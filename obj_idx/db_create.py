"""Run this module to (re)create DB tables (drops and recreates all tables)."""

from .db import Base, engine

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
