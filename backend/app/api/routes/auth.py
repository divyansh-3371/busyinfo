from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import DUMMY_PASSWORD_HASH, create_access_token, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    # Email lookup is case-insensitive - Postgres' default `=` on text is
    # case-sensitive, so without this, "Alice@Example.com" (a browser's or a
    # person's own capitalization, not a different account) would be rejected as
    # "wrong password" even with the exact right one. Only the comparison is
    # case-folded; the stored email and its casing are untouched.
    normalized_email = payload.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    # Deliberately the same error for "no such email" and "wrong password" - don't
    # leak which one was wrong. Just as deliberately, verify_password always runs -
    # against a real user's hash, or DUMMY_PASSWORD_HASH when there's no user at
    # all - so a request always pays the same bcrypt cost either way. Without
    # this, `user is None or not verify_password(...)` would short-circuit and
    # skip bcrypt entirely for an unknown email, making that case measurably
    # faster than a real-email-wrong-password rejection - a timing side channel
    # that lets an attacker enumerate which emails are actually registered.
    password_ok = verify_password(
        payload.password, user.password_hash if user else DUMMY_PASSWORD_HASH
    )
    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    token = create_access_token(subject=user.id)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
