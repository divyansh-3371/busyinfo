"""Auth edge cases from PLAN.md's edge-case list. Earlier in the build these were
checked by hand (TestClient + curl) but never committed as automated tests - this
closes that gap found during the Day 2 edge-case pass."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core.security import ALGORITHM, create_access_token
from app.core.config import get_settings
from app.main import app
from app.models.enums import Role


@pytest.fixture()
def client(db):
    from app.db.session import get_db

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_wrong_password_and_unknown_email_give_identical_error(client, make_user):
    make_user()  # creates user1@example.com / password123
    r_wrong_password = client.post(
        "/auth/login", json={"email": "user1@example.com", "password": "not-the-password"}
    )
    r_unknown_email = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "password123"}
    )
    assert r_wrong_password.status_code == r_unknown_email.status_code == 401
    assert r_wrong_password.json()["detail"] == r_unknown_email.json()["detail"]


def test_correct_login_returns_usable_token(client, make_user):
    user = make_user()
    r = client.post("/auth/login", json={"email": user.email, "password": "password123"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["id"] == user.id


def test_login_email_is_case_insensitive(client, make_user):
    """Regression test: Postgres' default `=` on text is case-sensitive, so
    "Alice@Example.com" was being rejected as a wrong password entirely, not just
    an unusual-looking one - a real lockout for anyone whose email client
    capitalizes, or who simply types the casing differently than it was seeded."""
    user = make_user()  # userN@example.com, all-lowercase
    mixed_case_email = user.email.replace("user", "User").replace("@example", "@Example")
    assert mixed_case_email != user.email  # sanity: the test actually changed the casing

    r = client.post("/auth/login", json={"email": mixed_case_email, "password": "password123"})
    assert r.status_code == 200
    assert r.json()["user"]["id"] == user.id

    r = client.post(
        "/auth/login", json={"email": user.email.upper(), "password": "password123"}
    )
    assert r.status_code == 200


def test_missing_token_401(client):
    assert client.get("/auth/me").status_code == 401


def test_garbage_token_401(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert r.status_code == 401


def test_expired_token_401(client, make_user):
    user = make_user()
    settings = get_settings()
    expired_payload = {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}
    expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=ALGORITHM)

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401


def test_token_signed_with_wrong_secret_401(client, make_user):
    user = make_user()
    forged = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "not-the-real-secret",
        algorithm=ALGORITHM,
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_token_for_deleted_user_401(client, make_user, db):
    user = make_user()
    token = create_access_token(subject=user.id)
    db.delete(user)
    db.flush()

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_role_change_takes_effect_without_a_new_token(client, make_user, db):
    """The JWT only ever encodes a user id, never a role claim - so a role change in
    the DB must take effect on the very next request, without needing to log in
    again for a fresh token."""
    user = make_user(role=Role.employee)
    token = create_access_token(subject=user.id)

    r = client.get("/reports/approvers", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403  # not an approver yet

    user.role = Role.approver
    db.flush()

    r = client.get("/reports/approvers", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200  # same token, now works - role was re-read, not cached
