"""Run this module to create DB tables"""

from . import db

db = db.db
db.drop_all()
db.create_all()
