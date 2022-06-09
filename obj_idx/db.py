"""Object Index Database Models"""

import datetime
from sqlalchemy.dialects.postgresql import UUID, JSONB
import flask_sqlalchemy
from . import app

app = app.app
db = flask_sqlalchemy.SQLAlchemy(app)

# https://docs.sqlalchemy.org/en/14/orm/basic_relationships.html#many-to-one
# https://flask-sqlalchemy.palletsprojects.com/en/2.x/models/
# db.Column(db.Text)
# db.Column(db.DateTime, onupdate=datetime.datetime.now)

class Object(db.Model):
    """Object table"""
    uuid = db.Column(UUID(as_uuid=True), primary_key=True)
    bucket = db.Column(db.String(63), nullable=False)
    key = db.Column(db.String(1023), nullable=False)
    obj_size = db.Column(db.BigInteger, nullable=False)
    checksum = db.Column(db.LargeBinary(32), index=True)
    ctime = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    mime = db.Column(db.String(255))
    completed = db.Column(db.Boolean, default=False, nullable=False)
    deleted = db.Column(db.Boolean, default=False, nullable=False)
    extra = db.Column(JSONB)
    __table_args__ = (db.Index('buckey', "bucket", "key"), )

class File(db.Model):
    """File table"""
    uuid = db.Column(UUID(as_uuid=True), primary_key=True)
    obj_uuid = db.Column(UUID(as_uuid=True), db.ForeignKey('object.uuid'), index=True, nullable=True)
    ctime = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    mtime = db.Column(db.DateTime, nullable=True)
    url = db.Column(db.String(2047), index=True, nullable=False)
    direct = db.Column(db.Boolean, default=True, nullable=False)
    partial = db.Column(db.Boolean, default=False, nullable=False)
    extra = db.Column(JSONB)
    ul_user = db.Column(db.String(15))
    ul_sw = db.Column(db.String(15))
    ul_host = db.Column(db.String(64))



#if __name__ == '__main__':
#    db.create_all()
