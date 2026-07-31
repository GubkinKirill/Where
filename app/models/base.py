from datetime import datetime
from enum import Enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    """Local naive timestamp: the app serves one site in a single timezone."""
    return datetime.now()


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)


def enum_column(enum_cls: type[Enum]) -> SAEnum:
    """Store enums as their string values, readable straight from sqlite3."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=24,
        values_callable=lambda cls: [member.value for member in cls],
    )
