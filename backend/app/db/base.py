"""Declarative base shared by every model, and the single import point Alembic uses
to discover all table metadata (see alembic/env.py)."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
