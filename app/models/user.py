from datetime import datetime
from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, enum_column
from app.models.enums import UserRole


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(256), default=None)
    full_name: Mapped[str] = mapped_column(String(150), default="")
    role: Mapped[UserRole] = mapped_column(enum_column(UserRole), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(default=True)
    # which credentials provider owns this account: "local" now, "ldap" later
    auth_provider: Mapped[str] = mapped_column(String(24), default="local")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(default=None)

    @property
    def display_name(self) -> str:
        return self.full_name or self.username

    def can(self, role: UserRole) -> bool:
        return self.is_active and self.role.at_least(role)

    def __str__(self) -> str:
        return self.display_name
