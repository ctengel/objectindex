"""Run this module to create DB tables"""

from . import db, app

with app.app.app_context():
    db = db.db
    db.drop_all()
    db.create_all()
