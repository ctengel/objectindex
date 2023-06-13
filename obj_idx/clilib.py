"""ObjectIndex client library"""

import datetime
import uuid
import requests


class File:
    """An ObjectIndex 'file'"""
    def __init__(self, oio: 'ObjectIndex', fil_uuid: uuid.UUID):
        self.oio = oio
        self.uuid = fil_uuid
        self.info = None
        self.object = None
        self.url = None
        self.s3_url = None
        self.object_url = None
        self.object_exists = None
    def set_info(self, info: dict):
        """Set info returned typically from GET /file/x"""
        self.info = info.copy()
        if info.get('file_object'):
            self.object = info['file_object'].copy()
    def set_upload(self, exists: bool, s3_url: str, object_url: str = None):
        """Set info from POST /upload/"""
        if exists is not None:
            self.object_exists = exists
        if s3_url:
            self.s3_url = s3_url
        if object_url:
            self.object_url = object_url
    def get_s3_url(self):
        """Return S3 object URL"""
        assert self.s3_url
        return self.s3_url
    def finish_upload(self):
        """Declare that an upload of this file is finished"""
        # NOTE this does not use ObjectIndex.put_object... maybe it should!
        # TODO determine if this URL is correct
        assert self.object_url
        result = requests.put(self.object_url, json={"completed": True})
        result.raise_for_json()
        self.object = result.json()
    def exists(self):
        """Has this file already been uploaded?"""
        assert self.object_exists is not None
        return self.object_exists


class ObjectIndex:
    """Interface with an ObjectIndex API instance"""
    def __init__(self, url, user=None, sw=None, host=None):
        self.url = url
        self.user = user
        self.sw = sw
        self.host = host

    def initiate_upload(self, url: str, bucket: str, obj_size: int, checksum: bytes,
                        direct: bool = True,
                        mtime: datetime.datetime = None,
                        filename: str = None,
                        mime: str = None,
                        partial: bool = False,
                        extra_file: dict = None,
                        extra_object: dict = None) -> File:
        """Kick off an upload of a file with given info and return a File object"""
        payload = {"url": url,
                   "bucket": bucket,
                   "obj_size": obj_size,
                   "checksum": checksum.hex(),
                   "direct": direct,
                   "partial": partial}
        if mtime:
            payload["mtime"] = mtime.isoformat()  # TODO consider timezone
        if self.user:
            payload["ul_user"] = self.user
        if self.sw:
            payload["ul_sw"] = self.sw
        if self.host:
            payload["ul_host"] = self.host
        if extra_file:
            payload["extra_file"] = extra_file
        if extra_object:
            payload["extra_object"] = extra_object
        if filename:
            payload["filename"] = filename
        if mime:
            payload["mime"] = mime
        result = requests.post(url + 'upload/', json=payload)
        result.raise_for_status()
        info = result.json()
        fileobj = File(self, uuid.UUID(info['file']['uuid']))
        fileobj.set_info(info['file'])
        fileobj.set_upload(exists=info['exists'],
                           s3_url=(info['download'] if info['exists'] else info['upload']['s3']),
                           object_url=(None if info['exists'] else info['upload']['finished']))
        return fileobj

    def put_object(self, object_uuid: uuid.UUID, info: dict):
        """PUT/PATCH an object"""
        # TODO implement
