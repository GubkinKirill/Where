from typing import Optional

from sqlalchemy.orm import Session

from app.auth.providers.base import CredentialsProvider
from app.auth.providers.local import LocalProvider, hash_password
from app.models.base import now
from app.models.user import User

# Order matters: the first provider that accepts the credentials wins.
PROVIDERS: list[CredentialsProvider] = [LocalProvider()]


def authenticate(db: Session, username: str, password: str) -> Optional[User]:
    username = (username or "").strip()
    if not username or not password:
        return None
    for provider in PROVIDERS:
        user = provider.authenticate(db, username, password)
        if user is not None:
            user.last_login_at = now()
            db.flush()
            return user
    return None


__all__ = ["PROVIDERS", "CredentialsProvider", "authenticate", "hash_password"]
