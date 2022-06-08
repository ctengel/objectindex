"""Object Index Database Models"""

from sqlalchemy.dialects.postgresql import UUID, JSONB
import flask_sqlalchemy
from . import app

app = app.app
db = flask_sqlalchemy.SQLAlchemy(app)

# https://docs.sqlalchemy.org/en/14/orm/basic_relationships.html#many-to-one
# https://flask-sqlalchemy.palletsprojects.com/en/2.x/models/
# TODO timestamps

# db.Column(db.Integer)
# db.Column(db.Boolean, default=False)
# db.Column(db.Text)
# db.Column(db.DateTime, default=datetime.datetime.now)
# db.Column(db.DateTime, onupdate=datetime.datetime.now)


class Object(db.Model):
    """Object table"""
    uuid = db.Column(UUID(as_uuid=True), primary_key=True)
    bucket = db.Column(db.String(63))
    key = db.Column(db.String(1023))
    size = db.Column(db.Integer)
    checksum = db.Column(db.LargeBinary(32))
    ctime = db.Column(db.DateTime)
    mime = db.Column(db.String(255))
    completed = db.Column(db.Boolean)
    deleted = db.Column(db.Boolean)
    extra = db.Column(JSONB)

class File(db.Model):
    """File table"""
    uuid = db.Column(UUID(as_uuid=True), primary_key=True)
    obj_uuid = db.Column(UUID(as_uuid=True), db.ForeignKey('object.uuid'), nullable=True)
    ctime = db.Column(db.DateTime)
    mtime = db.Column(db.DateTime)
    url = db.Column(db.String(2047))
    direct = db.Column(db.Boolean)
    partial = db.Column(db.Boolean)
    extra = db.Column(JSONB)
    user = db.Column(db.String(15))
    uploader = db.Column(db.String(15))
    hostname = db.Column(db.String(64))



#if __name__ == '__main__':
#    db.create_all()
