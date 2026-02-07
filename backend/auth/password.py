"""Password hashing utilities.

Hard constraint for v1: Argon2id password hashing.

For migration safety, we still accept bcrypt hashes for existing users and
upgrade them to Argon2id on successful login.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from argon2.low_level import Type


_argon2_hasher = PasswordHasher(type=Type.ID)

_PASSWORD_MIN_LENGTH = 8
_PASSWORD_MAX_LENGTH = 128


def validate_password_complexity(password: str) -> str | None:
    """Check password meets complexity requirements.

    Returns None if valid, or an error message string if invalid.
    """
    if len(password) < _PASSWORD_MIN_LENGTH:
        return f"Password must be at least {_PASSWORD_MIN_LENGTH} characters"
    if len(password) > _PASSWORD_MAX_LENGTH:
        return f"Password must be at most {_PASSWORD_MAX_LENGTH} characters"
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter"
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter"
    if not re.search(r"\d", password):
        return "Password must contain at least one digit"
    if not re.search(r"[^a-zA-Z0-9]", password):
        return "Password must contain at least one special character"
    return None


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    upgraded_hash: str | None = None


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return _argon2_hasher.hash(password)


def _verify_argon2(plain_password: str, hashed_password: str) -> VerifyResult:
    try:
        ok = _argon2_hasher.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return VerifyResult(ok=False)

    if not ok:
        return VerifyResult(ok=False)

    if _argon2_hasher.check_needs_rehash(hashed_password):
        return VerifyResult(ok=True, upgraded_hash=hash_password(plain_password))

    return VerifyResult(ok=True, upgraded_hash=None)


def _verify_bcrypt(plain_password: str, hashed_password: str) -> VerifyResult:
    ok = bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )
    if not ok:
        return VerifyResult(ok=False)

    # Always upgrade bcrypt to Argon2id after a successful verification.
    return VerifyResult(ok=True, upgraded_hash=hash_password(plain_password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password without upgrading."""
    return verify_password_with_upgrade(plain_password, hashed_password).ok


def verify_password_with_upgrade(
    plain_password: str, hashed_password: str
) -> VerifyResult:
    """Verify password and indicate whether the stored hash should be upgraded."""
    if not hashed_password:
        return VerifyResult(ok=False)

    if hashed_password.startswith("$argon2"):
        return _verify_argon2(plain_password, hashed_password)

    # bcrypt hashes usually start with $2a$, $2b$, or $2y$.
    if hashed_password.startswith("$2"):
        return _verify_bcrypt(plain_password, hashed_password)

    # Unknown scheme: fail closed.
    return VerifyResult(ok=False)
