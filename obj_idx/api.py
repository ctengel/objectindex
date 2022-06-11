"""Library Media Person RESTful API"""

import uuid
import hashlib
import flask_restx
from . import app
from . import db

app = app.app
api = flask_restx.Api(app,
                      version='0.1',
                      title='Object Index API',
                      description='API for storing info about Objects')
# TODO validate=True

uplns = api.namespace('upload', description='Upload operations')
filns = api.namespace('file', description='File operations')
objns = api.namespace('object', description='Object operations')

upl = api.model('UploadSub', {'mtime': flask_restx.fields.DateTime(),
                              'url': flask_restx.fields.String(required=True),
                              'direct': flask_restx.fields.Boolean(default=True),
                              'extra_file': flask_restx.fields.Object(),
                              'extra_object': flask_restx.fields.Object(),
                              'filename': flask_restx.fields.String(),
                              'ul_user': flask_restx.fields.String(),
                              'ul_sw': flask_restx.fields.String(),
                              'ul_host': flask_restx.fields.String(),
                              'partial': flask_restx.fields.Boolean(default=False),
                              'bucket':  flask_restx.fields.String(required=True),
                              'obj_size': flask_restx.fields.Integer(required=True),
                              'checksum':  flask_restx.fields.String(required=True),
                              'mime':  flask_restx.fields.String()})
obj = api.model('Object', {'ctime': flask_restx.fields.DateTime(readonly=True),
                           'files': # list of UUIDs, URLs
                           'url': flask_restx.fields.String(required=True),
                           'extra': flask_restx.fields.Object(),
                           'key': flask_restx.fields.String(readonly=True),
                           'completed': flask_restx.fields.Boolean(),
                           'deleted': flask_restx.fields.Boolean(),
                           'bucket':  flask_restx.fields.String(readonly=True),
                           'obj_size': flask_restx.fields.Integer(readonly=True),
                           'checksum':  flask_restx.fields.String(readonly=True),
                           'mime':  flask_restx.fields.String(),
                           'uuid': flask_restx.fields.String(readonly=True),
                           'download': flask_restx.fields.String(readonly=True)})
fil = api.model('File',  {'mtime': flask_restx.fields.DateTime(),
                          'url': flask_restx.fields.String(readonly=True),
                          'direct': flask_restx.fields.Boolean(),
                          'extra': flask_restx.fields.Object(),
                          'ul_user': flask_restx.fields.String(),
                          'ul_sw': flask_restx.fields.String(),
                          'ul_host': flask_restx.fields.String(),
                          'partial': flask_restx.fields.Boolean(),
                          'object': flask_restx.fields.Nested(obj),
                          'uuid': flask_restx.fields.String(readonly=True),
                          'ctime': flask_restx.fields.DateTime(readonly=True)})
ulr = api.model('UploadResult', {'file': flask_restx.fields.Nested(fil),
                                 'exists': flask_restx.fields.Boolean(),
                                 'upload': # obj with path to upload and path to object itself
                                 'download': flask_restx.fields.String(readonly=True)}) # URL for downlad


def get_dl_url(objobj):
    return [app.config.from_envvar('OBJIDX_S3'), objobj.bucket, objobj.key]

# flask_restx.fields.Integer(readonly=True, description='Task ID'),

@uplns.route('/')
class Upload(flask_restx.Resource):
    """Upload convenience API"""

    @libns.doc('submit_upload')
    @libns.expect(upl)
    @libns.marshal_with(ulr, code=201)
    def post(self):
        """Upload or get info"""
        exists = False
        my_obj = db.Object.query(checksum=api.payload.checksum).one_or_none()
        if my_obj:
            exists = True
            assert my_obj.obj_size = api.payload.obj_size
            assert my_obj.completed
            assert not my_obj.deleted
            if api.payload.mime and not my_obj.mime:
                exist_obj.mime = api.payload.mime
            if api.payload.extra_object and not my_obj.extra:
                my_obj.extra = api.payload.extra_object
        else:
            my_obj = db.Object(bucket=api.payload.bucket,
                               key= # TODO
                               obj_size=api.payload.obj_size,
                               checksum=api.payload.checksum,
                               mime=api.payload.mime,
                               extra=api.payload.extra_object)
            db.session.add(my_obj)
        my_file = db.File.query(url=api.payload.url, file_object=my_object).one_or_none()
        if my_file:
            assert exists
            assert my_file.direct = api.payload.direct
            assert my_file.partial = api.payload.partial
            if api.payload.mtime and not my_file.mtime:
                my_file.mtime = api.payload.mtime
            if api.payload.extra_file and not my_file.extra:
                my_file.extra = api.payload.extra_file
        else:
            my_file = db.File(file_object=my_obj,
                              mtime=api.payload.mtime,
                              url=api.payload.url,
                              direct=api.payload.direct,
                              partial=api.payload.partial,
                              extra=api.payload.extra_file,
                              ul_user=api.payload.ul_user,
                              ul_sw=api.payload.ul_sw,
                              ul_host=api.payload.host)
            db.session.add(my_file)

        db.db.session.commit()
        retobj =  {'file': my_file, 'exists': exists}
        if exists:
            retobj['download'] = get_dl_url(my_obj)
        else:
            retobj['upload'] = {'s3': get_dl_url(my_obj), 'finished': path_to(ObjOne)}
        return retobj, 201

@filns.route('/')
class FileList(flask_restx.Resource):
    """File search"""

    @filns.doc('search_files')
    @filns.marshal_list_with(fil)
    def get(self):
        parser = flask_restx.reqparse.RequestParser()
        parser.add_argument('url')
        args = parser.parse_args()
        return db.File.query(url=args.url).all()



@filns.route('/<fil_uuid>/')
@filns.response(404, 'File not found')
@filns.param('fil_uuid', 'File UUID')
class FileOne(flask_restx.Resource):
    """File instance"""

    @libns.doc('get_file')
    @libns.marshal_with(fil)
    def get(self, fil_uuid):
        """Get library media"""
        return db.Fil.query.get_or_404(fil_uuid)


@objns.route('/')
class ObjectList(flask_restx.Resource):
    """File search"""

    @objns.doc('search_files')
    @objns.marshal_list_with(obj)
    def get(self):
        parser = flask_restx.reqparse.RequestParser()
        parser.add_argument('checksum')
        args = parser.parse_args()
        return db.Object.query(checksum=args.checksum).all()



@objns.route('/<fil_uuid>/')
@objns.response(404, 'File not found')
@objns.param('obj_uuid', 'File UUID')
class ObjectOne(flask_restx.Resource):
    """File instance"""

    @libns.doc('get_object')
    @libns.marshal_with(fil)
    def get(self, obj_uuid):
        """Get library media"""
        return db.Obj.query.get_or_404(obj_uuid)
