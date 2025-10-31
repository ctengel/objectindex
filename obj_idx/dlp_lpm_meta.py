"""yt-dlp and lpm-index helper code

Enables easy addition of video info into OI
"""

import pathlib
import datetime
import json
from . import client

class NoMediaFile(Exception):
    pass

def read_info_json(filename):
    """Return data from a JSON file"""
    with open(filename, encoding="utf-8") as user_file:
        parsed_json = json.load(user_file)
    return parsed_json

def lpm2dict(library, person, media):
    if not library:
        return {}
    library = library.upper()
    if person:
        person = f"{library}{person.lower()}"
    if media:
        media = f"{library}{media.lower()}"
    return {'lpm-lib': library,
            'lpm-per': person,
            'lpm-med': media}


class DLPMetaData:
    data: dict = None
    ijfn: pathlib.Path = None
    partial: bool = False
    lpm: tuple = (None, None, None)

    def __init__(self, from_dict: dict = None, from_file: pathlib.Path = None, partial: bool = False):
        assert from_dict or from_file
        assert not (from_dict and from_file)
        if from_file:
            self.ijfn = from_file
            self.data = read_info_json(from_file)
        else:
            self.data = from_dict.copy()
        self.partial = partial
        
    def get_url(self):
        url = self.data.get('webpage_url')
        if not (url and url.startswith('http')):
            url = self.data.get('url')
        assert url.startswith('http')
        return url        

    def get_media_file(self) -> pathlib.Path:
        if self.data.get('_type') == 'playlist':
            raise NoMediaFile(f"No media for playlist {self.ijfn}")
        extension = self.data.get('ext')
        assert extension
        assert self.ijfn  # TODO drop this requirement
        base_file_name = self.ijfn.removesuffix('.info.json')
        assert base_file_name != self.ijfn
        media_file = base_file_name + "." + extension  # TODO use pathlib
        return pathlib.Path(media_file)
    
    def _get_media_file_verify(self):
        mf = self.get_media_file()
        if not mf.exists():
            raise NoMediaFile(f"Cannot find {mf}")
        return mf
    
    def add_lpm(self, library: str):
        media = None
        person = self.data.get('uploader')
        if self.data.get('creator'):
            person = self.data.get('creator')
        if self.partial:
            assert person
            # TODO don't use this deprecated thing
            starttime = datetime.datetime.utcfromtimestamp(self.data['timestamp']).isoformat()
            media = f'live-{person}-{starttime}-{self.data.get("id")}'
        else:
            if person:
                media = f'vid-{person}-{self.data.get("id")}'
            else:
                media = self.data.get("id")
        self.lpm = library, person, media
        return self.lpm
    
    def export_extra(self):
        extra = {'ytdl-info': self.data,
                 'ytdl-extractor': self.data['extractor_key'].lower(),
                'ytdl-id': f"{self.data['extractor_key'].lower()} {self.data['id']}"}
        extra.update(lpm2dict(*self.lpm))
        return extra

    def get_mtime(self):
        # TODO TZ
        return datetime.datetime.fromtimestamp(self.data['timestamp'])

    
    def upload(self, obj_idx, bucket):
        # TODO filename to delete when done
        mf = self._get_media_file_verify()
        url = self.get_url()
        mtime = self.get_mtime()
        flob = client.upload_local(mf, obj_idx, bucket,
                                   url=url,
                                   mtime=mtime,
                                   direct=False,
                                   partial=self.partial,
                                   extra=self.export_extra())
        assert flob
        return flob
