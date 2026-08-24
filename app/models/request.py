"""Requests an employee files from their cabinet: need something, something broke,
please take this back. Deliberately plain — a short text, a status and who closed it,
no assignees or priorities to maintain."""

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, enum_column
from app.models.directory import Employee
from app.models.enums import RequestKind, RequestStatus
from app.models.item import Item
from app.models.user import User


class EquipmentRequest(Base, TimestampMixin):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    kind: Mapped[RequestKind] = mapped_column(enum_column(RequestKind))
    status: Mapped[RequestStatus] = mapped_column(
        enum_column(RequestStatus), default=RequestStatus.NEW, index=True
    )
    text: Mapped[str] = mapped_column(Text, default="")
    # the unit the request is about, when the employee picked one of their own
    item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items.id"), default=None)

    resolution: Mapped[Optional[str]] = mapped_column(Text, default=None)
    closed_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    closed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), default=None
    )

    employee: Mapped[Employee] = relationship(lazy="joined")
    item: Mapped[Optional[Item]] = relationship(lazy="joined")
    closed_by: Mapped[Optional[User]] = relationship()

    @property
    def is_open(self) -> bool:
        return self.status.is_open
