"""Security utilities for JWT authentication."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings


def create_access_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token."""
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)

    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify a JWT token and return payload."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except jwt.PyJWTError:
        return None


def password_epoch(hashed_password: str | None) -> str:
    """Short digest of a stored password hash, used to bind a reset token to it.

    A JWT cannot be revoked, so a reset link would otherwise stay valid for its
    whole TTL — replayable after the victim has already used it. Embedding this
    digest makes the first successful reset invalidate the token by
    construction: the reset rotates ``hashed_password``, so the digest no longer
    matches. Stateless, so it needs no denylist and no migration.
    """
    return hashlib.sha256((hashed_password or "").encode("utf-8")).hexdigest()[:16]


def create_password_reset_token(
    subject: str | Any,
    current_password_hash: str | None,
    expires_delta: timedelta | None = None,
) -> str:
    """Single-use JWT for password reset.

    Short-lived (1h default). The `type` claim distinguishes it from access /
    refresh / magic-link tokens — a stolen reset token can't be used as an
    access token. The `pwe` claim binds it to the password in force at issue
    time, so redeeming it once invalidates it (see :func:`password_epoch`).
    """
    expire = datetime.now(UTC) + (expires_delta or timedelta(hours=1))
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "password_reset",
        "pwe": password_epoch(current_password_hash),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_magic_link_token(
    subject: str | Any,
    magic_link_epoch: int,
    expires_delta: timedelta | None = None,
) -> str:
    """Sign-in-by-email JWT. Short-lived (15 min default).

    The `mle` claim carries the user's magic-link epoch at issue time.
    Redeeming a link bumps the epoch, so the link that was used — and every
    other link still outstanding for that user — stops validating. This is what
    makes the link single-use; a JWT cannot be revoked any other way.
    """
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=15))
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "magic_link",
        "mle": magic_link_epoch,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_special_token(token: str, expected_type: str) -> dict[str, Any] | None:
    """Verify a non-access JWT (password_reset, magic_link) and require a
    specific `type` claim. Returns payload on success, None otherwise.
    """
    payload = verify_token(token)
    if payload is None:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
