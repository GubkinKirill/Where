from datetime import datetime
from enum import Enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# SQLite cannot ALTER in place: alembic rebuilds tables, and to do that it needs
# every constraint to have a name. This gives them all deterministic ones.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def now() -> datetime:
    """Local naive timestamp: the app serves one site in a single timezone."""
    return datetime.now()


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


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
