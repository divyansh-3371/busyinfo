"""Test DB fixtures: a dedicated `expenses_test` database (created if missing) against
the same local Postgres used for dev, with each test wrapped in a transaction that's
rolled back afterward for isolation. Tables are created directly from the SQLAlchemy
metadata (not via Alembic) since that's simpler and just as faithful for test purposes.
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.core.security import hash_password
from app.db.base import Base
from app.models.enums import Role
from app.models.user import User

ADMIN_URL = "postgresql+psycopg2://postgres:password@127.0.0.1:5433/postgres"
TEST_URL = "postgresql+psycopg2://postgres:password@127.0.0.1:5433/expenses_test"


@pytest.fixture(scope="session")
def engine():
    admin_engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'expenses_test'")
        ).scalar()
        if not exists:
            conn.execute(text("CREATE DATABASE expenses_test"))
    admin_engine.dispose()

    eng = create_engine(TEST_URL)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    # autoflush=False to match the app's real SessionLocal (db/session.py) exactly -
    # this default used to differ, and it silently hid a real bug: a route that
    # mutated a row and re-queried it without an explicit flush passed every test
    # (autoflush=True papered over it) while being wrong in production, where
    # nothing flushes until told to. See update_line's fix for the actual bug.
    session = sessionmaker(bind=connection, autoflush=False)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def make_user(db):
    counter = {"n": 0}

    def _make(role: Role = Role.employee, name: str | None = None) -> User:
        counter["n"] += 1
        user = User(
            email=f"user{counter['n']}@example.com",
            name=name or f"User {counter['n']}",
            role=role,
            password_hash=hash_password("password123"),
        )
        db.add(user)
        db.flush()
        return user

    return _make
