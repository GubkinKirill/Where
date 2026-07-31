from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.directory import Employee
from app.models.enums import ItemStatus
from app.models.item import Item, ItemAttribute, ItemType
from app.models.user import User
from app.schemas.item import ItemFilter, ItemForm
from app.services.errors import ServiceError
from app.services.location import LocationRef
from app.services.movements import register_item
from app.services.numbering import next_inv_number

SEARCHABLE_COLUMNS = (
    Item.inv_number,
    Item.legacy_number,
    Item.serial_number,
    Item.name,
    Item.model,
    Item.manufacturer,
)


def get_item(db: Session, item_id: int) -> Optional[Item]:
    return db.get(Item, item_id)


def get_by_inv_number(db: Session, inv_number: str) -> Optional[Item]:
    return db.scalars(
        select(Item).where(Item.inv_number == inv_number.strip().upper())
    ).first()


def create_item(
    db: Session,
    *,
    form: ItemForm,
    location: LocationRef,
    actor: Optional[User] = None,
    attributes: Optional[dict[str, str]] = None,
    comment: Optional[str] = None,
) -> Item:
    item_type = db.get(ItemType, form.type_id)
    if item_type is None:
        raise ServiceError("Тип единицы не найден.")

    item = Item(inv_number=next_inv_number(db, item_type.code), type_id=item_type.id)
    _apply_form(item, form)
    _apply_attributes(item, attributes)
    register_item(db, item=item, at=location, actor=actor, comment=comment)
    return item


def update_item(
    db: Session,
    *,
    item: Item,
    form: ItemForm,
    attributes: Optional[dict[str, str]] = None,
) -> Item:
    if form.type_id != item.type_id:
        item_type = db.get(ItemType, form.type_id)
        if item_type is None:
            raise ServiceError("Тип единицы не найден.")
        # the inventory number keeps its original prefix on purpose: it is printed
        # on a sticker already stuck to the hardware
    _apply_form(item, form)
    _apply_attributes(item, attributes)
    db.flush()
    return item


def legacy_number_duplicates(
    db: Session, legacy_number: Optional[str], exclude_id: Optional[int] = None
) -> list[Item]:
    """Old case numbers do repeat; we warn instead of forbidding."""
    if not legacy_number:
        return []
    stmt = select(Item).where(Item.legacy_number == legacy_number.strip())
    if exclude_id is not None:
        stmt = stmt.where(Item.id != exclude_id)
    return list(db.scalars(stmt.order_by(Item.inv_number)))


def search_items(db: Session, filters: ItemFilter) -> list[Item]:
    stmt = select(Item).outerjoin(Employee, Item.loc_employee_id == Employee.id)

    if filters.q:
        pattern = f"%{filters.q.strip()}%"
        conditions = [column.ilike(pattern) for column in SEARCHABLE_COLUMNS]
        conditions.append(Employee.full_name.ilike(pattern))
        stmt = stmt.where(or_(*conditions))

    if filters.type_id:
        stmt = stmt.where(Item.type_id == filters.type_id)
    if filters.status:
        stmt = stmt.where(Item.status == filters.status)
    if filters.loc_kind:
        stmt = stmt.where(Item.loc_kind == filters.loc_kind)
    if filters.room_id:
        stmt = stmt.where(Item.loc_room_id == filters.room_id)
    if filters.employee_id:
        stmt = stmt.where(Item.loc_employee_id == filters.employee_id)
    if filters.storage_place_id:
        stmt = stmt.where(Item.loc_storage_place_id == filters.storage_place_id)
    if filters.parent_item_id:
        stmt = stmt.where(Item.loc_parent_item_id == filters.parent_item_id)
    if filters.department_id:
        stmt = stmt.where(Employee.department_id == filters.department_id)
    if not filters.include_written_off and filters.status is not ItemStatus.WRITTEN_OFF:
        stmt = stmt.where(Item.status != ItemStatus.WRITTEN_OFF)

    return list(db.scalars(stmt.order_by(Item.inv_number).limit(filters.limit)))


def count_items(db: Session, *, include_written_off: bool = False) -> int:
    stmt = select(func.count(Item.id))
    if not include_written_off:
        stmt = stmt.where(Item.status != ItemStatus.WRITTEN_OFF)
    return db.scalar(stmt) or 0


# --- internals ---------------------------------------------------------------


def _apply_form(item: Item, form: ItemForm) -> None:
    item.type_id = form.type_id
    item.name = form.name
    item.legacy_number = form.legacy_number
    item.manufacturer = form.manufacturer
    item.model = form.model
    item.serial_number = form.serial_number
    item.status = form.status
    item.condition_note = form.condition_note
    item.purchase_date = form.purchase_date
    item.warranty_until = form.warranty_until
    item.notes = form.notes


def _apply_attributes(item: Item, attributes: Optional[dict[str, str]]) -> None:
    if attributes is None:
        return
    cleaned = {
        key.strip(): value.strip()
        for key, value in attributes.items()
        if key.strip() and value.strip()
    }
    existing = {attribute.key: attribute for attribute in item.attributes}

    for key, value in cleaned.items():
        if key in existing:
            existing[key].value = value
        else:
            item.attributes.append(ItemAttribute(key=key, value=value))

    for key, attribute in existing.items():
        if key not in cleaned:
            item.attributes.remove(attribute)
