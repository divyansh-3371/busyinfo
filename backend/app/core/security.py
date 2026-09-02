from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

ALGORITHM = "HS256"


def hash_password(plain_password: str) -> str:
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash (shouldn't happen with hashes we generated ourselves).
        return False


# A real bcrypt hash of a password nobody has, computed once at import time. Used
# by the login route when no matching user is found, so a login attempt spends
# exactly one bcrypt comparison either way - closes the "unknown email vs. wrong
# password" timing side-channel documented in NOTES.md. Without this, an
# unknown-email login returns almost instantly (a DB miss, no hashing at all)
# while a real-email-wrong-password login takes the full ~100-300ms bcrypt cost -
# an easily measurable difference an attacker can use to enumerate which emails
# are actually registered, even though the response body is identical either way.
DUMMY_PASSWORD_HASH = hash_password("no-such-user-timing-safety-placeholder")


def create_access_token(*, subject: int) -> str:
    """Issue a JWT whose only claim is the user id. Role is deliberately NOT baked in
    as a claim - every request re-reads the user's current role from the database, so
    a role change takes effect immediately rather than waiting for the token to expire."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Returns the user id encoded in the token, or None if it's missing, malformed,
    expired, or signed with a different secret."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError:
        return None
    subject = payload.get("sub")
    if subject is None:
        return None
    try:
        return int(subject)
    except (TypeError, ValueError):
        return None
