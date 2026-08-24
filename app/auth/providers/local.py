from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User

_hasher = PasswordHasher()

PROVIDER_NAME = "local"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(user: User, password: str) -> bool:
    """Check a password without signing anybody in — used to confirm a password change."""
    if not user.password_hash:
        return False
    try:
        _hasher.verify(user.password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


class LocalProvider:
    """Username and password stored in our own table, hashed with argon2."""

    name = PROVIDER_NAME

    def authenticate(self, db: Session, username: str, password: str) -> Optional[User]:
        user = db.scalars(select(User).where(User.username == username)).first()
        if user is None or not user.is_active or user.auth_provider != self.name:
            return None
        if not user.password_hash:
            return None
        try:
            _hasher.verify(user.password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return None
        if _hasher.check_needs_rehash(user.password_hash):
            user.password_hash = _hasher.hash(password)
        return user
