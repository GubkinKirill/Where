"""Whose the equipment is, which is not the same question as where it is.

Most units belong to the enterprise. Some arrive with a project — bought for it,
brought by the customer, to be handed back when the project ends — and those must
be tellable apart at a glance, however far they wander across shelves and people.

Belonging is an ordinary editable field, not a placement: it changes when paperwork
changes, not when somebody carries the thing to another room.
"""

from datetime import date
from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, enum_column
from app.models.enums import ProjectStatus


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    customer: Mapped[Optional[str]] = mapped_column(String(160), default=None)
    starts_on: Mapped[Optional[date]] = mapped_column(default=None)
    ends_on: Mapped[Optional[date]] = mapped_column(default=None)
    status: Mapped[ProjectStatus] = mapped_column(
        enum_column(ProjectStatus), default=ProjectStatus.ACTIVE, index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)

    @property
    def is_open(self) -> bool:
        return self.status.is_open

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"
