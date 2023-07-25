"""ObjectIndex client library"""

import datetime
import uuid
from urllib.parse import urljoin
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
    def get_object_url(self):
        """Return the OI Object URL"""
        if not self.object_url:
            assert self.info
            # TODO note this is not ideal
            self.object_url = f"/object/{self.info['file_object']['uuid']}/"
        return self.object_url
    def get_s3_url(self):
        """Return S3 object URL"""
        if not self.s3_url:
            self.s3_url = self.oio.get(urljoin(self.get_object_url(),'download'))
        return self.s3_url
    def finish_upload(self):
        """Declare that an upload of this file is finished"""
        # NOTE this does not use ObjectIndex.put_object... maybe it should!
        assert self.object_url
        self.object = self.oio.put(self.object_url, json={"completed": True})
        # TODO should this update self.object_exists?
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

    # TODO combine put/post/get to single function

    def put(self, url, json):
        """Run an API PUT/PATCH"""
        result = requests.put(urljoin(self.url, url), json=json)
        result.raise_for_status()
        return result.json()

    def post(self, url, json):
        """Run an API POST"""
        result = requests.post(urljoin(self.url, url), json=json)
        result.raise_for_status()
        return result.json()

    def get(self, url, params=None):
        """Run an API GET"""
        result = requests.get(urljoin(self.url, url), params=params)
        result.raise_for_status()
        return result.json()

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
        info = self.post('upload/', json=payload)
        fileobj = File(self, uuid.UUID(info['file']['uuid']))
        fileobj.set_info(info['file'])
        # NOTE the object_url is relative to the OI API URL
        #      this is OK though because fileobj.oio.url has it
        fileobj.set_upload(exists=info['exists'],
                           s3_url=(info['download'] if info['exists'] else info['upload']['s3']),
                           object_url=(None if info['exists'] else info['upload']['finished']))
        return fileobj

    def put_object(self, object_uuid: uuid.UUID, info: dict):
        """PUT/PATCH an object"""
        # TODO implement

    def search_files(self, params):
        """Search for files with given parameters"""
        files = []
        for file in self.get('file/', params):
            file_obj = File(self, file['uuid'])
            file_obj.set_info(file)
            files.append(file_obj)
        return files
