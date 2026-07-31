from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.i18n import LOCATION_SNAPSHOT_TEMPLATES
from app.models.directory import Employee, Room, StoragePlace
from app.models.enums import LocationKind
from app.models.item import Item


@dataclass(frozen=True)
class LocationRef:
    """A place an item can be. Immutable, passed into the movement service."""

    kind: LocationKind
    parent_item_id: Optional[int] = None
    storage_place_id: Optional[int] = None
    employee_id: Optional[int] = None
    room_id: Optional[int] = None
    external_note: Optional[str] = None

    @classmethod
    def inside(cls, parent_item_id: int) -> "LocationRef":
        return cls(LocationKind.INSIDE, parent_item_id=parent_item_id)

    @classmethod
    def storage(cls, storage_place_id: int) -> "LocationRef":
        return cls(LocationKind.STORAGE, storage_place_id=storage_place_id)

    @classmethod
    def person(cls, employee_id: int, room_id: Optional[int] = None) -> "LocationRef":
        return cls(LocationKind.PERSON, employee_id=employee_id, room_id=room_id)

    @classmethod
    def room(cls, room_id: int) -> "LocationRef":
        return cls(LocationKind.ROOM, room_id=room_id)

    @classmethod
    def external(cls, note: str) -> "LocationRef":
        return cls(LocationKind.EXTERNAL, external_note=note)

    @classmethod
    def written_off(cls) -> "LocationRef":
        return cls(LocationKind.WRITTEN_OFF)

    @classmethod
    def of(cls, item: Item) -> "LocationRef":
        return cls(
            kind=item.loc_kind,
            parent_item_id=item.loc_parent_item_id,
            storage_place_id=item.loc_storage_place_id,
            employee_id=item.loc_employee_id,
            room_id=item.loc_room_id,
            external_note=item.loc_external_note,
        )

    def same_as(self, other: "LocationRef") -> bool:
        return self == other


def describe_location(db: Session, ref: LocationRef) -> str:
    """Human readable snapshot, stored on the movement so history survives renames."""
    target = ""
    if ref.kind is LocationKind.INSIDE:
        parent = db.get(Item, ref.parent_item_id)
        target = f"{parent.inv_number} {parent.name}" if parent else "?"
    elif ref.kind is LocationKind.STORAGE:
        place = db.get(StoragePlace, ref.storage_place_id)
        target = place.full_path if place else "?"
    elif ref.kind is LocationKind.PERSON:
        employee = db.get(Employee, ref.employee_id)
        target = employee.short_name if employee else "?"
        room = db.get(Room, ref.room_id) if ref.room_id else None
        if room:
            target = f"{target}, каб. {room.number}"
    elif ref.kind is LocationKind.ROOM:
        room = db.get(Room, ref.room_id)
        target = room.number if room else "?"
    elif ref.kind is LocationKind.EXTERNAL:
        target = ref.external_note or "?"

    return LOCATION_SNAPSHOT_TEMPLATES[ref.kind].format(target=target)
