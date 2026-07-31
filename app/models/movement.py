from datetime import date, datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, enum_column, now
from app.models.directory import Employee, Room, StoragePlace
from app.models.enums import LocationKind, MovementReason
from app.models.item import Item
from app.models.user import User


class Movement(Base):
    """Append-only log. The single source of truth for where an item is.

    Both sides of the move are stored twice: as foreign keys, so reports and links
    keep working, and as a text label taken at the time of the move, so history stays
    readable after directories are renamed.
    """

    __tablename__ = "movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    moved_at: Mapped[datetime] = mapped_column(default=now, index=True)
    reason: Mapped[MovementReason] = mapped_column(enum_column(MovementReason))
    comment: Mapped[Optional[str]] = mapped_column(Text, default=None)

    moved_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), default=None)
    recipient_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id"), default=None
    )
    expected_return_date: Mapped[Optional[date]] = mapped_column(default=None)
    returned_at: Mapped[Optional[datetime]] = mapped_column(default=None)

    # where it came from; empty on the very first record of an item
    from_kind: Mapped[Optional[LocationKind]] = mapped_column(
        enum_column(LocationKind), default=None
    )
    from_parent_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items.id"), default=None)
    from_storage_place_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("storage_places.id"), default=None
    )
    from_employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), default=None)
    from_room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rooms.id"), default=None)
    from_external_note: Mapped[Optional[str]] = mapped_column(String(200), default=None)
    from_label: Mapped[str] = mapped_column(String(300), default="")

    to_kind: Mapped[LocationKind] = mapped_column(enum_column(LocationKind))
    to_parent_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items.id"), default=None)
    to_storage_place_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("storage_places.id"), default=None
    )
    to_employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), default=None)
    to_room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rooms.id"), default=None)
    to_external_note: Mapped[Optional[str]] = mapped_column(String(200), default=None)
    to_label: Mapped[str] = mapped_column(String(300), default="")

    item: Mapped[Item] = relationship(foreign_keys=[item_id])
    moved_by: Mapped[Optional[User]] = relationship()
    recipient: Mapped[Optional[Employee]] = relationship(foreign_keys=[recipient_employee_id])

    from_parent_item: Mapped[Optional[Item]] = relationship(foreign_keys=[from_parent_item_id])
    from_storage_place: Mapped[Optional[StoragePlace]] = relationship(
        foreign_keys=[from_storage_place_id]
    )
    from_employee: Mapped[Optional[Employee]] = relationship(foreign_keys=[from_employee_id])
    from_room: Mapped[Optional[Room]] = relationship(foreign_keys=[from_room_id])

    to_parent_item: Mapped[Optional[Item]] = relationship(foreign_keys=[to_parent_item_id])
    to_storage_place: Mapped[Optional[StoragePlace]] = relationship(
        foreign_keys=[to_storage_place_id]
    )
    to_employee: Mapped[Optional[Employee]] = relationship(foreign_keys=[to_employee_id])
    to_room: Mapped[Optional[Room]] = relationship(foreign_keys=[to_room_id])

    @property
    def is_overdue(self) -> bool:
        return (
            self.returned_at is None
            and self.expected_return_date is not None
            and self.expected_return_date < date.today()
        )
