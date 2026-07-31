from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, enum_column
from app.models.enums import StoragePlaceKind


class Department(Base, TimestampMixin):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(120))

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Room(Base, TimestampMixin):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(16), unique=True)
    floor: Mapped[Optional[int]] = mapped_column(default=None)
    description: Mapped[Optional[str]] = mapped_column(String(200), default=None)

    def __str__(self) -> str:
        return self.number


class StoragePlace(Base, TimestampMixin):
    """Cabinet / shelf / cell, nested through parent_id. Each place has its own QR code."""

    __tablename__ = "storage_places"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[StoragePlaceKind] = mapped_column(
        enum_column(StoragePlaceKind), default=StoragePlaceKind.SHELF
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("storage_places.id"), default=None
    )
    notes: Mapped[Optional[str]] = mapped_column(String(400), default=None)

    parent: Mapped[Optional["StoragePlace"]] = relationship(
        remote_side="StoragePlace.id", back_populates="children"
    )
    children: Mapped[list["StoragePlace"]] = relationship(
        back_populates="parent", order_by="StoragePlace.name"
    )

    @property
    def full_path(self) -> str:
        parts, place, guard = [], self, 0
        while place is not None and guard < 20:
            parts.append(place.name)
            place = place.parent
            guard += 1
        return " / ".join(reversed(parts))

    def __str__(self) -> str:
        return self.full_path


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150), index=True)
    position: Mapped[Optional[str]] = mapped_column(String(120), default=None)
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id"), default=None
    )
    default_room_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rooms.id"), default=None
    )
    is_active: Mapped[bool] = mapped_column(default=True)

    department: Mapped[Optional[Department]] = relationship()
    default_room: Mapped[Optional[Room]] = relationship()

    @property
    def short_name(self) -> str:
        """«Петров Иван Сергеевич» -> «Петров И. С.» — fewer personal data on screen."""
        parts = self.full_name.split()
        if len(parts) < 2:
            return self.full_name
        initials = " ".join(f"{part[0]}." for part in parts[1:3])
        return f"{parts[0]} {initials}"

    def __str__(self) -> str:
        return self.short_name
