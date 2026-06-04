"""Object Index RESTful API (FastAPI)."""

import uuid
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import Session

from .config import get_settings
from .db import File, Object, get_session, select
from .schemas import (
    ConflictResponse,
    DetailResponse,
    FileRead,
    ObjectRead,
    ObjectUpdate,
    S3Link,
    UploadRequest,
    UploadResult,
)

NOT_FOUND = {404: {"model": DetailResponse}}

ACCEPT_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
REPLACE_CHAR = "_"
LIKE_ESCAPE_CHAR = "\\"


def sanitize_filename(requested_name):
    """Santize a filename into a usable key"""
    translation_table = str.maketrans({ch: REPLACE_CHAR
                                       for ch in set(requested_name) - set(ACCEPT_CHARS)})
    return requested_name.translate(translation_table)


def escape_like_prefix(value):
    """Escape user-provided LIKE wildcards before appending our own wildcard."""
    return (value.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
                 .replace("%", LIKE_ESCAPE_CHAR + "%")
                 .replace("_", LIKE_ESCAPE_CHAR + "_"))


app = FastAPI(
    title="Object Index API",
    version="0.3.0",
    description="API for storing info about Objects",
)


def get_dl_url(objobj: Object) -> str:
    """Get a URLish list of server, bucket, key"""
    return f"{get_settings().s3}{objobj.bucket}/{objobj.key}"


@app.post("/upload/", status_code=201, response_model=UploadResult,
          responses={
              400: {"model": DetailResponse,
                    "description": "Invalid checksum"},
              409: {"model": ConflictResponse,
                    "description": "Object size mismatch, an upload of an object "
                                   "with the same checksum may currently be in "
                                   "progress, the object was previously deleted, "
                                   "or the existing file's direct/partial status "
                                   "does not match"},
              404: {"model": DetailResponse,
                    "description": "Unknown bucket"}
          })
def upload(payload: UploadRequest, session: Session = Depends(get_session)):
    """Upload or get info"""
    # TODO consider raise HTTPException instead of JSONResponse
    #      (currently differs to return object ID on 409)
    exists = False
    try:
        checksum = bytes.fromhex(payload.checksum)
    except ValueError:
        raise HTTPException(status_code=400, detail="checksum must be hex")
    if payload.bucket not in get_settings().buckets:
        raise HTTPException(status_code=404, detail="Unknown bucket")
    my_obj = session.exec(
        select(Object).where(Object.checksum == checksum)
    ).one_or_none()
    if my_obj:
        exists = True
        if my_obj.obj_size != payload.obj_size:
            return JSONResponse(status_code=409,
                                content={"message": "Object size mismatch",
                                         "object_uuid": str(my_obj.uuid)})
        if not my_obj.completed:
            # Upload was initiated before but not finished
            if not my_obj.deleted:
                # We believe it may still be in progress so declare a conflict
                return JSONResponse(
                    status_code=409,
                    content={"message": "Conflict: an upload of an object with "
                                        "the same checksum may currently be in "
                                        "progress",
                             "object_uuid": str(my_obj.uuid)})
            # The failed upload has been cleared/deleted so allow restart
            my_obj.deleted = False
            exists = False
        if my_obj.deleted:
            # Object was intentionally deleted; 409 here, 410 for GET data
            return JSONResponse(status_code=409, content={"message": "object previously deleted",
                                                          "object_uuid": str(my_obj.uuid)})
        if payload.mime and not my_obj.mime:
            my_obj.mime = payload.mime
        if payload.extra_object and not my_obj.extra:
            my_obj.extra = payload.extra_object
    else:
        my_obj = Object(bucket=payload.bucket,
                        key=f"{checksum.hex()}-{sanitize_filename(payload.filename)}",
                        obj_size=payload.obj_size,
                        checksum=checksum,
                        mime=payload.mime,
                        extra=payload.extra_object)
        session.add(my_obj)
        session.flush()
    my_file = session.exec(
        select(File).where(File.url == payload.url, File.obj_uuid == my_obj.uuid)
    ).one_or_none()
    if my_file:
        # NOTE: We do not assert "exists" here to allow retries of cleared failed uploads
        if payload.direct != my_file.direct or payload.partial != my_file.partial:
            return JSONResponse(status_code=409, content={"message": "partial/direct status does not match existing file",
                                                          "file_uuid": str(my_file.uuid),
                                                          "object_uuid": str(my_obj.uuid)})
        if payload.mtime and not my_file.mtime:
            my_file.mtime = payload.mtime
        if payload.extra_file and not my_file.extra:
            my_file.extra = payload.extra_file
    else:
        my_file = File(file_object=my_obj,
                       mtime=payload.mtime,
                       url=payload.url,
                       direct=payload.direct,
                       partial=payload.partial,
                       extra=payload.extra_file,
                       ul_user=payload.ul_user,
                       ul_sw=payload.ul_sw,
                       ul_host=payload.ul_host)
        session.add(my_file)
    session.commit()
    session.refresh(my_file)
    result = {"file": my_file, "exists": exists}
    if exists:
        result["download"] = get_dl_url(my_obj)
    else:
        # NOTE the s3 URL is NOW really a URL
        result["upload"] = {"s3": get_dl_url(my_obj),
                            "finished": f"/object/{my_obj.uuid}/"}
    return result


@app.get("/file/", response_model=list[FileRead],
         responses={400: {"model": DetailResponse,
                          "description": "Invalid url/extra query"}})
def search_files(url: Optional[str] = None,
                 extra: Optional[str] = None,
                 session: Session = Depends(get_session)):
    """Search for a file by source URL or by an extra-JSON tag"""
    if url and extra:
        raise HTTPException(status_code=400,
                            detail="Cannot search by both url and extra")
    if not url and not extra:
        raise HTTPException(status_code=400,
                            detail="Must search by url or extra")
    if extra:
        key, sep, value = extra.partition("=")
        if sep != "=":
            raise HTTPException(status_code=400, detail="extra must be key=value")
        stmt = select(File).where(File.extra[key].astext == value)
        return session.exec(stmt).all()
    if url and url.endswith("*"):
        url_prefix = escape_like_prefix(url[:-1])
        stmt = select(File).where(
            File.url.like(f"{url_prefix}%", escape=LIKE_ESCAPE_CHAR)
        )
        return session.exec(stmt).all()
    return session.exec(select(File).where(File.url == url)).all()


@app.get("/file/{fil_uuid}/", response_model=FileRead, responses=NOT_FOUND)
def get_file(fil_uuid: uuid.UUID, session: Session = Depends(get_session)):
    """Get a single file"""
    my_file = session.get(File, fil_uuid)
    if my_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return my_file


@app.get("/object/", response_model=list[ObjectRead],
         responses={400: {"model": DetailResponse,
                          "description": "Invalid checksum"}})
def search_objects(checksum: str, session: Session = Depends(get_session)):
    """Search for objects by checksum"""
    try:
        checksum_bytes = bytes.fromhex(checksum)
    except ValueError:
        raise HTTPException(status_code=400, detail="checksum must be hex")
    return session.exec(
        select(Object).where(Object.checksum == checksum_bytes)
    ).all()


@app.get("/object/{obj_uuid}/", response_model=ObjectRead, responses=NOT_FOUND)
def get_object(obj_uuid: uuid.UUID, session: Session = Depends(get_session)):
    """Get a single object"""
    my_obj = session.get(Object, obj_uuid)
    if my_obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return my_obj


@app.put("/object/{obj_uuid}/", response_model=ObjectRead,
         responses={
             400: {"model": DetailResponse,
                   "description": "Cannot set both completed and deleted"},
             404: {"model": DetailResponse},
         })
def update_object(obj_uuid: uuid.UUID,
                  payload: ObjectUpdate,
                  session: Session = Depends(get_session)):
    """Let us know an upload is completed (or deleted)"""
    my_obj = session.get(Object, obj_uuid)
    if my_obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    new_completed = payload.completed
    new_deleted = payload.deleted
    if not my_obj.completed and not my_obj.deleted:
        if new_completed and new_deleted:
            raise HTTPException(status_code=400,
                                detail="Cannot set both completed and deleted")
        if new_completed or new_deleted:
            if new_completed:
                my_obj.completed = True
            if new_deleted:
                my_obj.deleted = True
            session.commit()
            session.refresh(my_obj)
    return my_obj


@app.get("/object/{obj_uuid}/download", response_model=S3Link, responses=NOT_FOUND)
def download_object(obj_uuid: uuid.UUID, session: Session = Depends(get_session)):
    """Get S3 download info for object"""
    my_obj = session.get(Object, obj_uuid)
    if my_obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    if my_obj.deleted:
        raise HTTPException(status_code=410, detail="Object deleted")
    if not my_obj.completed:
        raise HTTPException(status_code=503, detail="Object upload in progress")
    return {"presigned": get_dl_url(my_obj)}
