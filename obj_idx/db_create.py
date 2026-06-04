"""Run this module to (re)create DB tables (drops and recreates all tables)."""

from .db import SQLModel, engine

SQLModel.metadata.drop_all(engine)
SQLModel.metadata.create_all(engine)
