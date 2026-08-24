from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, enum_column
from app.models.directory import Employee
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
    # the person behind the account: whose cabinet this login opens. Staff accounts
    # may leave it empty, an employee account without it has nothing to show.
    employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id"), unique=True, default=None
    )

    employee: Mapped[Optional[Employee]] = relationship(lazy="joined")

    @property
    def display_name(self) -> str:
        if self.employee is not None and not self.full_name:
            return self.employee.short_name
        return self.full_name or self.username

    @property
    def is_staff(self) -> bool:
        return self.role.is_staff

    def can(self, role: UserRole) -> bool:
        return self.is_active and self.role.at_least(role)

    def __str__(self) -> str:
        return self.display_name
