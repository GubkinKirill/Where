from typing import Optional, Protocol

from sqlalchemy.orm import Session

from app.models.user import User


class CredentialsProvider(Protocol):
    """Credential check, kept separate so LDAP/AD can be added as another provider."""

    name: str

    def authenticate(self, db: Session, username: str, password: str) -> Optional[User]:
        ...
