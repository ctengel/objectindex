"""Object Index GUI"""

from urllib.parse import urlparse, urlunparse
from pathlib import PurePath
import flask
from . import client

def get_api():
    """Get obj_index api object"""
    if 'oiapi' not in flask.g:
        # TODO let user authenticate into app
        flask.g.oiapi = client.get_obj_idx(flask.current_app.config['OBJIDX_URL'],
                                           flask.current_app.config['OBJIDX_AUTH'])

    return flask.g.oiapi


def close_api(e=None):
    """Remove obj_index api object"""
    _ = flask.g.pop('oiapi', None)

    #if  is not None:
    #    db.close()

app = flask.Flask(__name__)
app.config.from_envvar('OBJIDX_GUI_SETTINGS')

app.teardown_appcontext(close_api)


def up_url(fullurl):
    """Generate the "up" URL for a given URL"""
    parsed = urlparse(fullurl)
    assert parsed.scheme
    assert not parsed.params
    if parsed.scheme == 'file':
        assert "." not in parsed.netloc
        assert not parsed.query
        assert not parsed.fragment
        if parsed.path.endswith('*'):
            newpath = str(PurePath(parsed.path).parent.parent.joinpath('*'))
        else:
            newpath = str(PurePath(parsed.path).parent.joinpath('*'))
        return urlunparse(('file', parsed.netloc, newpath, None, None, None))
    assert "." in parsed.netloc
    return urlunparse((parsed.scheme, parsed.netloc, '*', None, None, None))



@app.route("/")
def home():
    """Home page as jumping off point to other stuff"""
    return flask.render_template('home.html')

@app.route("/file/<fileid>")
def show_file(fileid):
    """Display details about a file"""
    objidx = get_api()
    myfile = objidx.get_file(fileid)
    tags = []
    for key, value in myfile.info['extra'].items():
        if isinstance(value, str):
            tags.append({"key": key, "value": value})
    return flask.render_template('file.html', fo=myfile, tags=tags, up=up_url(myfile.info['url']))

@app.route("/object/<objectid>/")
def show_object(objectid):
    """Redirect or list files of an object"""
    objidx = get_api()
    myobj = objidx.get_object(objectid)
    numfiles = len(myobj['files'])
    if numfiles == 1:
        # TODO 302,303,307
        return flask.redirect(flask.url_for('show_file', fileid=myobj['files'][0]['uuid']))
    #TODO 200 or 300
    return flask.render_template('object.html', oo=myobj)

@app.route("/file/")
def search_files():
    """List of files or redirect randomly"""
    playlist = (flask.request.args.get('playlist', 'off') == 'on')
    random = (flask.request.args.get('playlist', 'off') == 'on')
    url = flask.request.args.get('url')
    extra = None
    if flask.request.args.get('extrak'):
        assert flask.request.args.get('extrav')  # TODO relax to allow bool
        extra = f"{flask.request.args.get('extrak')}={flask.request.args.get('extrav')}"
    else:
        assert not flask.request.args.get('extrav')
    uuid = flask.request.args.get('uuid')
    if uuid:
        assert not extra
        assert not url
        assert not random
        assert not playlist
        # TODO consider 308
        return flask.redirect(flask.url_for('show_file', fileid=uuid), 301)
    assert url or extra
    assert not (url and extra)
    objidx = get_api()
    result_list = objidx.search_files({'url': url, 'extra': extra})
    if random and result_list:
        assert not playlist
        return flask.redirect(flask.url_for('show_file', fileid=random.choice(result_list).uuid))
    if playlist:
        assert False
        # TODO return playlist
    up_star = None
    param = None
    if url:
        up_star = up_url(url)
        param = url
    if extra:
        param = extra
    return flask.render_template('list.html', fos=result_list, up=up_star, param=param)


@app.route("/object/")
def search_objects():
    """Find an object by checksum or uuid"""
    checksum = flask.request.args.get('checksum')
    uuid = flask.request.args.get('uuid')
    if uuid:
        assert not checksum
        return flask.redirect(flask.url_for('show_object', objectid=uuid), 301)
    assert checksum
    objidx = get_api()
    objobj = objidx.search_object(checksum)[0]
    return flask.redirect(flask.url_for('show_object', objectid=objobj['uuid']))

@app.route("/object/<objectid>/download")
def download_object(objectid):
    """Redirect to presigned S3 URL for object"""
    assert False
    # stream or presigned
    # TODO see #22 / #13
