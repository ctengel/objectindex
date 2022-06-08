"""Run this module to create DB tables"""

from . import db

db = db.db
db.create_all()
