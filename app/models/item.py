from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, enum_column, now
from app.models.directory import Employee, Room, StoragePlace
from app.models.enums import ItemStatus, LocationKind

# Location cache columns on Item. Written only by services.movements.move_item(),
# which is enforced by the guard in services/location_guard.py.
LOCATION_COLUMNS = (
    "loc_kind",
    "loc_parent_item_id",
    "loc_storage_place_id",
    "loc_employee_id",
    "loc_room_id",
    "loc_external_note",
    "loc_since",
)

# Exactly one target per location kind. A person may additionally carry a room
# override, everything else must be empty.
LOCATION_SHAPE_CHECK = """
(loc_kind = 'inside'
    AND loc_parent_item_id IS NOT NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_external_note IS NULL)
OR (loc_kind = 'storage'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NOT NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_external_note IS NULL)
OR (loc_kind = 'person'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NOT NULL AND loc_external_note IS NULL)
OR (loc_kind = 'room'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NOT NULL AND loc_external_note IS NULL)
OR (loc_kind = 'external'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_external_note IS NOT NULL)
OR (loc_kind = 'written_off'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_external_note IS NULL)
"""


class ItemType(Base, TimestampMixin):
    """Editable through the UI, never hardcoded. `code` doubles as the number prefix."""

    __tablename__ = "item_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    is_container: Mapped[bool] = mapped_column(default=False)
    icon: Mapped[str] = mapped_column(String(8), default="")
    # attribute keys the item form suggests for this type; it does not restrict them
    suggested_attributes: Mapped[list[str]] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(default=100)
    is_active: Mapped[bool] = mapped_column(default=True)

    def __str__(self) -> str:
        return self.name


class NumberSequence(Base):
    """Per-prefix counter. Numbers of written off items are never reused."""

    __tablename__ = "number_sequences"

    prefix: Mapped[str] = mapped_column(String(8), primary_key=True)
    last_value: Mapped[int] = mapped_column(default=0)


class Item(Base, TimestampMixin):
    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint(LOCATION_SHAPE_CHECK, name="location_shape"),
        CheckConstraint(
            "loc_parent_item_id IS NULL OR loc_parent_item_id <> id",
            name="not_inside_itself",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inv_number: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    # number painted on the case before this system existed, e.g. "235-70";
    # duplicates happen in practice, so it is indexed but not unique
    legacy_number: Mapped[Optional[str]] = mapped_column(String(32), index=True, default=None)
    type_id: Mapped[int] = mapped_column(ForeignKey("item_types.id"))
    name: Mapped[str] = mapped_column(String(200))
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100), default=None)
    model: Mapped[Optional[str]] = mapped_column(String(100), default=None)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), index=True, default=None)
    status: Mapped[ItemStatus] = mapped_column(
        enum_column(ItemStatus), default=ItemStatus.RESERVE, index=True
    )
    condition_note: Mapped[Optional[str]] = mapped_column(Text, default=None)
    purchase_date: Mapped[Optional[date]] = mapped_column(default=None)
    warranty_until: Mapped[Optional[date]] = mapped_column(default=None)
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)
    # reserved for a future hardware collector agent; nothing writes it yet
    auto_data: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    # for container items assembled to a checklist: what this kit should contain
    kit_template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kit_templates.id"), default=None
    )

    loc_kind: Mapped[LocationKind] = mapped_column(enum_column(LocationKind), index=True)
    loc_parent_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("items.id"), index=True, default=None
    )
    loc_storage_place_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("storage_places.id"), index=True, default=None
    )
    loc_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id"), index=True, default=None
    )
    loc_room_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rooms.id"), index=True, default=None
    )
    loc_external_note: Mapped[Optional[str]] = mapped_column(String(200), default=None)
    loc_since: Mapped[datetime] = mapped_column(default=now)

    type: Mapped[ItemType] = relationship(lazy="joined")
    parent_item: Mapped[Optional["Item"]] = relationship(
        remote_side="Item.id", back_populates="contents"
    )
    contents: Mapped[list["Item"]] = relationship(
        back_populates="parent_item", order_by="Item.inv_number"
    )
    storage_place: Mapped[Optional[StoragePlace]] = relationship()
    employee: Mapped[Optional[Employee]] = relationship()
    room: Mapped[Optional[Room]] = relationship()
    kit_template: Mapped[Optional["KitTemplate"]] = relationship()  # noqa: F821
    attributes: Mapped[list["ItemAttribute"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ItemAttribute.key"
    )

    @property
    def prefix(self) -> str:
        return self.inv_number.split("-")[0]

    @property
    def is_written_off(self) -> bool:
        return self.status is ItemStatus.WRITTEN_OFF

    def __str__(self) -> str:
        return f"{self.inv_number} {self.name}"


class ItemAttribute(Base):
    """Free-form extra fields: Raspberry Pi image, MAC, IP, project, board revision."""

    __tablename__ = "item_attributes"
    __table_args__ = (UniqueConstraint("item_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(String(500), default="")

    item: Mapped[Item] = relationship(back_populates="attributes")
