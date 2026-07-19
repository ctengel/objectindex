"""Object Index RESTful API (FastAPI)."""

import uuid
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlmodel import Session
from simpler_objects.auth import OP_READ, OP_WRITE, OP_LIST

from .config import get_settings, get_auth
from .db import File, Object, get_session, select
from .schemas import (
    ConflictResponse,
    DetailResponse,
    FileRead,
    ObjectBrief,
    ObjectRead,
    ObjectUpdate,
    S3Link,
    UploadRequest,
    UploadResult,
)
from .common import reconcile_mime_ext

NOT_FOUND = {404: {"model": DetailResponse}}
# Possible on every endpoint once OBJIDX_AUTH_CONFIG is set
AUTH_RESPONSES = {
    401: {"model": DetailResponse,
          "description": "Missing/invalid credentials (auth enabled)"},
    403: {"model": DetailResponse,
          "description": "Insufficient permissions (auth enabled)"},
}

ACCEPT_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
REPLACE_CHAR = "_"
LIKE_ESCAPE_CHAR = "\\"


def sanitize_filename(requested_name):
    """Santize a filename into a usable key"""
    if not requested_name:
        return None
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
    version="0.4.0",
    description="API for storing info about Objects",
)

# Basic in the challenge (mirroring simpler-objects) so browsers can prompt;
# AuthConfig.authenticate accepts Bearer too.
WWW_AUTHENTICATE = 'Basic realm="objectindex", charset="UTF-8"'


def authenticated_client(request: Request) -> Optional[str]:
    """Resolve the request to a client name, or None when auth is off."""
    auth = get_auth()
    if auth is None:
        return None
    name = auth.authenticate(request.headers.get("authorization"))
    if name is None:
        raise HTTPException(status_code=401,
                            headers={"WWW-Authenticate": WWW_AUTHENTICATE})
    return name


def require_bucket_op(client_name: Optional[str], bucket: str, operation: str):
    """403 unless the client may perform ``operation`` on ``bucket``.

    No-op when auth is off (``client_name`` is then None from the dependency).
    """
    auth = get_auth()
    if auth is None:
        return
    if not auth.allowed(client_name, bucket, operation):
        raise HTTPException(status_code=403)


def get_dl_url(objobj: Object) -> str:
    """Get a URLish list of server, bucket, key"""
    return f"{get_settings().s3}{objobj.bucket}/{objobj.key}"


@app.post("/upload/", status_code=201, response_model=UploadResult,
          responses={
              **AUTH_RESPONSES,
              200: {"model": UploadResult,
                    "description": "Object already present; download URL returned"},
              201: {"model": UploadResult,
                    "description": "New object recorded; PUT the bytes to the "
                                   "returned upload URL"},
              400: {"model": DetailResponse,
                    "description": "Invalid checksum, object size mismatch, or "
                                   "direct/partial status mismatch"},
              409: {"model": ConflictResponse,
                    "description": "An upload of an object with the same "
                                   "checksum may currently be in progress / "
                                   "failed"},
              410: {"model": DetailResponse,
                    "description": "Object was previously deleted"},
              404: {"model": DetailResponse,
                    "description": "Unknown bucket"}
          })
def upload(payload: UploadRequest,
           response: Response,
           session: Session = Depends(get_session),
           client_name: Optional[str] = Depends(authenticated_client)):
    """Upload or get info"""
    # NOTE 409 (in-progress) keeps a JSONResponse so it can carry the object ID
    #      an admin needs to scrub the failed upload; every other error uses
    #      HTTPException since there is no semi-automated resolution path.
    # Authz before the unknown-bucket 404 so an ungranted client cannot probe
    # which buckets exist.
    require_bucket_op(client_name, payload.bucket, OP_WRITE)
    if client_name is not None:
        # Attribution comes from authentication, not the client's say-so.
        # ul_user is varchar(15); a longer client name is truncated.
        payload.ul_user = client_name[:15]
    exists = False
    in_progress = False
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
            raise HTTPException(
                status_code=400,
                detail=f"Object size mismatch (existing object {my_obj.uuid})")
        if not my_obj.completed:
            # Upload was initiated before but not finished
            if not my_obj.deleted:
                # May still be in progress: we still record a File for this
                # (new) source URL below, but the client must not upload bytes
                # or get a download URL, so we declare a conflict at the end.
                in_progress = True
            else:
                # The failed upload has been cleared/deleted so allow restart
                my_obj.deleted = False
                exists = False
        if my_obj.deleted:
            # Object was intentionally deleted; 410 here and for GET data
            raise HTTPException(
                status_code=410,
                detail=f"object previously deleted (existing object {my_obj.uuid})")
        if payload.mime and not my_obj.mime:
            my_obj.mime = payload.mime
        if payload.extra_object and not my_obj.extra:
            my_obj.extra = payload.extra_object
    else:
        my_obj_fn, my_obj_mime = reconcile_mime_ext(sanitize_filename(payload.filename), payload.mime)
        my_obj = Object(bucket=payload.bucket,
                        key=f"{checksum.hex()}-{my_obj_fn}" if my_obj_fn else checksum.hex(),
                        obj_size=payload.obj_size,
                        checksum=checksum,
                        mime=my_obj_mime,
                        extra=payload.extra_object)
        session.add(my_obj)
        session.flush()
    my_file = session.exec(
        select(File).where(File.url == payload.url, File.obj_uuid == my_obj.uuid)
    ).one_or_none()
    if my_file:
        # NOTE: We do not assert "exists" here to allow retries of cleared failed uploads
        if payload.direct != my_file.direct or payload.partial != my_file.partial:
            raise HTTPException(
                status_code=400,
                detail=f"partial/direct status does not match existing file "
                       f"{my_file.uuid} (object {my_obj.uuid})")
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
    if in_progress:
        # The File is recorded, but an upload of the same checksum may still be
        # in flight: tell the client not to upload and not to expect a download.
        return JSONResponse(
            status_code=409,
            content={"message": "Conflict: an upload of an object with the "
                                "same checksum may currently be in progress",
                     "object_uuid": str(my_obj.uuid),
                     "file_uuid": str(my_file.uuid)})
    result = {"file": my_file, "exists": exists}
    if exists:
        result["download"] = get_dl_url(my_obj)
        response.status_code = 200
        return result
    # NOTE the s3 URL is NOW really a URL (decorator default status_code=201)
    result["upload"] = {"s3": get_dl_url(my_obj),
                        "finished": f"/object/{my_obj.uuid}/"}
    return result


@app.get("/file/", response_model=list[FileRead],
         responses={**AUTH_RESPONSES,
                    400: {"model": DetailResponse,
                          "description": "Invalid url/extra query"}})
def search_files(url: Optional[str] = None,
                 extra: Optional[str] = None,
                 session: Session = Depends(get_session),
                 _client_name: Optional[str] = Depends(authenticated_client)):
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


@app.get("/file/{fil_uuid}/", response_model=FileRead,
         responses={**AUTH_RESPONSES, **NOT_FOUND})
def get_file(fil_uuid: uuid.UUID, session: Session = Depends(get_session),
             _client_name: Optional[str] = Depends(authenticated_client)):
    """Get a single file"""
    my_file = session.get(File, fil_uuid)
    if my_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return my_file


@app.get("/object/", response_model=list[ObjectRead],
         responses={**AUTH_RESPONSES,
                    400: {"model": DetailResponse,
                          "description": "Invalid checksum"}})
def search_objects(checksum: str, session: Session = Depends(get_session),
                   _client_name: Optional[str] = Depends(authenticated_client)):
    """Search for objects by checksum"""
    try:
        checksum_bytes = bytes.fromhex(checksum)
    except ValueError:
        raise HTTPException(status_code=400, detail="checksum must be hex")
    return session.exec(
        select(Object).where(Object.checksum == checksum_bytes)
    ).all()


@app.get("/buckets/{bucket}/", response_model=list[ObjectBrief],
         responses={**AUTH_RESPONSES,
                    404: {"model": DetailResponse,
                          "description": "Unknown bucket"}})
def list_bucket_objects(bucket: str, session: Session = Depends(get_session),
                        client_name: Optional[str] = Depends(authenticated_client)):
    """List brief metadata for every object in a bucket.

    Returns ``ObjectBrief`` for each object (including the
    ``completed``/``deleted`` flags) but without embedded files or the
    ``extra`` blob.
    """
    # Authz before the 404 so an ungranted client cannot probe bucket names
    require_bucket_op(client_name, bucket, OP_LIST)
    if bucket not in get_settings().buckets:
        raise HTTPException(status_code=404, detail="Unknown bucket")
    return session.exec(select(Object).where(Object.bucket == bucket)).all()


@app.get("/object/{obj_uuid}/", response_model=ObjectRead,
         responses={**AUTH_RESPONSES, **NOT_FOUND})
def get_object(obj_uuid: uuid.UUID, session: Session = Depends(get_session),
               _client_name: Optional[str] = Depends(authenticated_client)):
    """Get a single object"""
    my_obj = session.get(Object, obj_uuid)
    if my_obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return my_obj


@app.put("/object/{obj_uuid}/", response_model=ObjectRead,
         responses={
             **AUTH_RESPONSES,
             400: {"model": DetailResponse,
                   "description": "Cannot set both completed and deleted"},
             404: {"model": DetailResponse},
             409: {"model": DetailResponse,
                   "description": "Object already cleared/deleted"},
         })
def update_object(obj_uuid: uuid.UUID,
                  payload: ObjectUpdate,
                  session: Session = Depends(get_session),
                  client_name: Optional[str] = Depends(authenticated_client)):
    """Let us know an upload is completed (or deleted)"""
    # TODO(#96): serialize concurrent clear/complete with a row lock
    my_obj = session.get(Object, obj_uuid)
    if my_obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    require_bucket_op(client_name, my_obj.bucket, OP_WRITE)
    new_completed = payload.completed
    new_deleted = payload.deleted
    if new_completed and my_obj.deleted:
        # Upload was cleared/deleted (perhaps accidentally) but the bytes
        # finished landing afterwards; surface the conflict instead of
        # silently dropping the completion and orphaning the object.
        raise HTTPException(status_code=409,
                            detail="Object was cleared/deleted; "
                                   "completion rejected")
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


@app.get("/object/{obj_uuid}/download", response_model=S3Link,
         responses={**AUTH_RESPONSES, **NOT_FOUND})
def download_object(obj_uuid: uuid.UUID, session: Session = Depends(get_session),
                    client_name: Optional[str] = Depends(authenticated_client)):
    """Get S3 download info for object"""
    my_obj = session.get(Object, obj_uuid)
    if my_obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    require_bucket_op(client_name, my_obj.bucket, OP_READ)
    if my_obj.deleted:
        raise HTTPException(status_code=410, detail="Object deleted")
    if not my_obj.completed:
        raise HTTPException(status_code=503, detail="Object upload in progress")
    return {"presigned": get_dl_url(my_obj)}
