"""Library Media Person RESTful API"""

import uuid
import flask_restx
from . import app
from . import db

class Checksum(flask_restx.fields.Raw):
    """Render binary field from DB as hex"""
    def format(self, value):
        return value.hex()

app = app.app
api = flask_restx.Api(app,
                      version='0.1',
                      title='Object Index API',
                      description='API for storing info about Objects')
# TODO validate=True

uplns = api.namespace('upload', description='Upload operations')
filns = api.namespace('file', description='File operations')
objns = api.namespace('object', description='Object operations')

# TODO add link to full file URL (i.e. GET /file/abcd)
abf = api.model('BriefFile', {'uuid': flask_restx.fields.String(readonly=True),
                              'url': flask_restx.fields.String(readonly=True)})
                              #'link': flask_restx.fields.String(readonly=True)})
s3l = api.model('S3Link', {'server': flask_restx.fields.String(),
                           'bucket': flask_restx.fields.String(),
                           'key': flask_restx.fields.String()})
ull = api.model('UploadLinks', {'finished': flask_restx.fields.String(readonly=True),
                               's3': flask_restx.fields.Nested(s3l, readonly=True)})
upl = api.model('UploadSub', {'mtime': flask_restx.fields.DateTime(),
                              'url': flask_restx.fields.String(required=True),
                              'direct': flask_restx.fields.Boolean(default=True),
                              'extra_file': flask_restx.fields.Raw(),
                              'extra_object': flask_restx.fields.Raw(),
                              'filename': flask_restx.fields.String(),
                              'ul_user': flask_restx.fields.String(),
                              'ul_sw': flask_restx.fields.String(),
                              'ul_host': flask_restx.fields.String(),
                              'partial': flask_restx.fields.Boolean(default=False),
                              'bucket':  flask_restx.fields.String(required=True),
                              'obj_size': flask_restx.fields.Integer(required=True),
                              'checksum':  flask_restx.fields.String(required=True),
                              'mime':  flask_restx.fields.String()})
# TODO need to include S3 URL somehow here...
obj = api.model('Object', {'ctime': flask_restx.fields.DateTime(readonly=True),
                           'files': flask_restx.fields.List(flask_restx.fields.Nested(abf)),
                           #'url': flask_restx.fields.String(required=True),
                           'extra': flask_restx.fields.Raw(),
                           'key': flask_restx.fields.String(readonly=True),
                           'completed': flask_restx.fields.Boolean(),
                           'deleted': flask_restx.fields.Boolean(),
                           'bucket':  flask_restx.fields.String(readonly=True),
                           'obj_size': flask_restx.fields.Integer(readonly=True),
                           'checksum':  Checksum(readonly=True),
                           'mime':  flask_restx.fields.String(),
                           'uuid': flask_restx.fields.String(readonly=True)})#,
                           #'download': flask_restx.fields.String(readonly=True)})
fil = api.model('File',  {'mtime': flask_restx.fields.DateTime(),
                          'url': flask_restx.fields.String(readonly=True),
                          'direct': flask_restx.fields.Boolean(),
                          'extra': flask_restx.fields.Raw(),
                          'ul_user': flask_restx.fields.String(),
                          'ul_sw': flask_restx.fields.String(),
                          'ul_host': flask_restx.fields.String(),
                          'partial': flask_restx.fields.Boolean(),
                          'file_object': flask_restx.fields.Nested(obj),
                          'uuid': flask_restx.fields.String(readonly=True),
                          'ctime': flask_restx.fields.DateTime(readonly=True)})
ulr = api.model('UploadResult', {'file': flask_restx.fields.Nested(fil),
                                 'exists': flask_restx.fields.Boolean(),
                                 'upload': flask_restx.fields.Nested(ull),
                                 'download': flask_restx.fields.Nested(s3l, readonly=True)})


def get_dl_url(objobj):
    """Get a URLish list of server, bucket, key"""
    return {'server': app.config['OBJIDX_S3'],
            'bucket': objobj.bucket,
            'key': objobj.key}

# flask_restx.fields.Integer(readonly=True, description='Task ID'),

@uplns.route('/')
class Upload(flask_restx.Resource):
    """Upload convenience API"""

    @uplns.doc('submit_upload')
    @uplns.expect(upl)
    @uplns.marshal_with(ulr, code=201)
    def post(self):
        """Upload or get info"""
        exists = False
        checksum = bytes.fromhex(api.payload['checksum'])
        assert api.payload['bucket'] in app.config['OBJIDX_BUCKETS']
        my_obj = db.Object.query.filter_by(checksum=checksum).one_or_none()
        if my_obj:
            exists = True
            assert my_obj.obj_size == api.payload['obj_size']
            assert my_obj.completed
            assert not my_obj.deleted
            if api.payload['mime'] and not my_obj.mime:
                my_obj.mime = api.payload['mime']
            if api.payload.get('extra_object') and not my_obj.extra:
                my_obj.extra = api.payload['extra_object']
        else:
            my_obj = db.Object(bucket=api.payload['bucket'],
                               key="{}-{}".format(checksum.hex(), api.payload['filename']),
                               obj_size=api.payload['obj_size'],
                               checksum=checksum,
                               mime=api.payload['mime'],
                               extra=api.payload.get('extra_object'))
            db.db.session.add(my_obj)
        my_file = db.File.query.filter_by(url=api.payload['url'], file_object=my_obj).one_or_none()
        if my_file:
            assert exists
            assert my_file.direct == api.payload['direct']
            assert my_file.partial == api.payload['partial']
            if api.payload['mtime'] and not my_file.mtime:
                my_file.mtime = api.payload['mtime']
            if api.payload.get('extra_file') and not my_file.extra:
                my_file.extra = api.payload['extra_file']
        else:
            my_file = db.File(file_object=my_obj,
                              mtime=api.payload['mtime'],
                              url=api.payload['url'],
                              direct=api.payload['direct'],
                              partial=api.payload.get('partial'),
                              extra=api.payload.get('extra_file'),
                              ul_user=api.payload['ul_user'],
                              ul_sw=api.payload['ul_sw'],
                              ul_host=api.payload['ul_host'])
            db.db.session.add(my_file)

        db.db.session.commit()
        #print(my_file.__dict__)
        retobj =  {'file': my_file, 'exists': exists}
        #retobj['file']['object'] = my_obj
        if exists:
            retobj['download'] = get_dl_url(my_obj)
        else:
            retobj['upload'] = {'s3': get_dl_url(my_obj),
                                'finished': api.url_for(ObjectOne, obj_uuid=my_obj.uuid)}
        return retobj, 201


@filns.route('/')
class FileList(flask_restx.Resource):
    """File search"""

    @filns.doc('search_files',
               params={'url': {'description': 'Source URL to search for',
                               'type': 'string'}})
    @filns.marshal_list_with(fil)
    def get(self):
        """Search for a file"""
        parser = flask_restx.reqparse.RequestParser()
        parser.add_argument('url')
        args = parser.parse_args()
        return db.File.query.filter_by(url=args.url).all()


@filns.route('/<fil_uuid>/')
@filns.response(404, 'File not found')
@filns.param('fil_uuid', 'File UUID')
class FileOne(flask_restx.Resource):
    """File instance"""

    @filns.doc('get_file')
    @filns.marshal_with(fil)
    def get(self, fil_uuid):
        """Get library media"""
        return db.File.query.get_or_404(uuid.UUID(fil_uuid))


@objns.route('/')
class ObjectList(flask_restx.Resource):
    """Object search"""

    @objns.doc('search_objects',
               params={'checksum': {'description': 'Checksum to search for',
                                    'type': 'string'}})
    @objns.marshal_list_with(obj)
    def get(self):
        """Search for a file"""
        parser = flask_restx.reqparse.RequestParser()
        parser.add_argument('checksum')
        args = parser.parse_args()
        checksum = bytes.fromhex(args['checksum'])
        return db.Object.query.filter_by(checksum=checksum).all()


@objns.route('/<obj_uuid>/')
@objns.response(404, 'File not found')
@objns.param('obj_uuid', 'File UUID')
class ObjectOne(flask_restx.Resource):
    """File instance"""

    @objns.doc('get_object')
    @objns.marshal_with(obj)
    def get(self, obj_uuid):
        """Get library media"""
        return db.Object.query.get_or_404(uuid.UUID(obj_uuid))

    @objns.doc('put_object')
    @objns.marshal_with(obj)
    @objns.expect(obj)
    def put(self, obj_uuid):
        """Let us know an upload is completed"""
        myobj = db.Object.query.get_or_404(uuid.UUID(obj_uuid))
        if api.payload['completed'] and not myobj.completed:
            myobj.completed = True
            db.db.session.commit()
        return myobj
