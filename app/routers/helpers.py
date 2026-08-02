from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.directory import Department, Employee, Room, StoragePlace
from app.models.enums import LocationKind
from app.models.item import Item, ItemType
from app.models.kit import KitTemplate
from app.services.errors import MoveError
from app.services.location import LocationRef


def int_or_none(value: Any) -> Optional[int]:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def location_from_form(db: Session, form) -> LocationRef:
    """Turn the placement part of a submitted form into a LocationRef."""
    raw_kind = (form.get("loc_kind") or "").strip()
    if not raw_kind:
        raise MoveError("Не выбран вид размещения.")
    try:
        kind = LocationKind(raw_kind)
    except ValueError as exc:
        raise MoveError("Неизвестный вид размещения.") from exc

    if kind is LocationKind.INSIDE:
        return LocationRef.inside(int_or_none(form.get("parent_item_id")))
    if kind is LocationKind.STORAGE:
        return LocationRef.storage(int_or_none(form.get("storage_place_id")))
    if kind is LocationKind.ROOM:
        return LocationRef.room(int_or_none(form.get("room_id")))
    if kind is LocationKind.EXTERNAL:
        return LocationRef.external((form.get("external_note") or "").strip())
    if kind is LocationKind.WRITTEN_OFF:
        return LocationRef.written_off()

    employee_id = int_or_none(form.get("employee_id"))
    room_id = int_or_none(form.get("room_id"))
    if room_id is None and employee_id is not None:
        employee = db.get(Employee, employee_id)
        room_id = employee.default_room_id if employee else None
    return LocationRef.person(employee_id, room_id)


def attributes_from_form(form) -> dict[str, str]:
    keys = form.getlist("attr_key")
    values = form.getlist("attr_value")
    return {key: value for key, value in zip(keys, values)}


def form_choices(db: Session) -> dict[str, Any]:
    """Directory contents every item/placement form needs."""
    return {
        "types": list(db.scalars(select(ItemType).order_by(ItemType.sort_order, ItemType.name))),
        "employees": list(
            db.scalars(
                select(Employee).where(Employee.is_active).order_by(Employee.full_name)
            )
        ),
        "rooms": list(db.scalars(select(Room).order_by(Room.number))),
        "departments": list(db.scalars(select(Department).order_by(Department.code))),
        "storage_places": list(
            db.scalars(select(StoragePlace).order_by(StoragePlace.code))
        ),
        "containers": list(
            db.scalars(
                select(Item)
                .join(ItemType, Item.type_id == ItemType.id)
                .where(ItemType.is_container.is_(True))
                .order_by(Item.inv_number)
            )
        ),
        "kit_templates": list(
            db.scalars(select(KitTemplate).where(KitTemplate.is_active).order_by(KitTemplate.name))
        ),
    }
