"""The only place where an item's location may change.

Every change is a record in the movement log; the columns on Item are a cache that
this module keeps in sync. Nothing else is allowed to write them — see location_guard.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import now
from app.models.directory import Employee, Room, StoragePlace
from app.models.enums import ItemStatus, LocationKind, MovementReason
from app.models.item import Item
from app.models.movement import Movement
from app.models.user import User
from app.services import tree
from app.services.errors import MoveError
from app.services.location import LocationRef, describe_location
from app.services.location_guard import location_write


def move_item(
    db: Session,
    *,
    item: Item,
    to: LocationRef,
    reason: MovementReason,
    actor: Optional[User] = None,
    recipient_employee_id: Optional[int] = None,
    expected_return_date: Optional[date] = None,
    comment: Optional[str] = None,
    moved_at: Optional[datetime] = None,
) -> Movement:
    """Move one item and log it. Single transaction — caller commits."""
    if item.is_written_off:
        raise MoveError(
            f"Единица {item.inv_number} списана. Списанные единицы не перемещаются."
        )

    origin = LocationRef.of(item)
    _validate(db, item, to)
    if to.same_as(origin):
        raise MoveError(f"Единица {item.inv_number} уже находится в этом размещении.")

    if reason is MovementReason.ISSUE and recipient_employee_id is None:
        recipient_employee_id = to.employee_id

    movement = _build_movement(
        db,
        item=item,
        origin=origin,
        target=to,
        reason=reason,
        actor=actor,
        recipient_employee_id=recipient_employee_id,
        expected_return_date=expected_return_date,
        comment=comment,
        moved_at=moved_at,
    )
    db.add(movement)

    if reason is MovementReason.RETURN:
        _close_open_issue(db, item, movement.moved_at)

    with location_write(db):
        _apply(item, to)
        if to.kind is LocationKind.WRITTEN_OFF:
            item.status = ItemStatus.WRITTEN_OFF
        db.flush()
    return movement


def register_item(
    db: Session,
    *,
    item: Item,
    at: LocationRef,
    actor: Optional[User] = None,
    comment: Optional[str] = None,
) -> Movement:
    """Put a brand new item on the books: initial placement plus its first log record."""
    _validate(db, item, at)
    with location_write(db):
        _apply(item, at)
        db.add(item)
        db.flush()

    movement = _build_movement(
        db,
        item=item,
        origin=None,
        target=at,
        reason=MovementReason.REGISTER,
        actor=actor,
        comment=comment,
    )
    db.add(movement)
    db.flush()
    return movement


def issue_item(
    db: Session,
    *,
    item: Item,
    employee_id: Optional[int],
    room_id: Optional[int] = None,
    actor: Optional[User] = None,
    expected_return_date: Optional[date] = None,
    comment: Optional[str] = None,
    moved_at: Optional[datetime] = None,
) -> Movement:
    """Hand an item to an employee. A spare item becomes an item in use."""
    movement = move_item(
        db,
        item=item,
        to=LocationRef.person(employee_id, room_id),
        reason=MovementReason.ISSUE,
        actor=actor,
        expected_return_date=expected_return_date,
        comment=comment,
        moved_at=moved_at,
    )
    if item.status is ItemStatus.RESERVE:
        item.status = ItemStatus.IN_USE
    db.flush()
    return movement


def return_to_storage(
    db: Session,
    *,
    item: Item,
    storage_place_id: Optional[int],
    actor: Optional[User] = None,
    comment: Optional[str] = None,
    moved_at: Optional[datetime] = None,
) -> Movement:
    """Take an item back and put it on a shelf; closes the open issue record."""
    if storage_place_id is None:
        raise MoveError("Выберите место хранения, куда принимаете единицу.")
    movement = move_item(
        db,
        item=item,
        to=LocationRef.storage(storage_place_id),
        reason=MovementReason.RETURN,
        actor=actor,
        comment=comment,
        moved_at=moved_at,
    )
    if item.status is ItemStatus.IN_USE:
        item.status = ItemStatus.RESERVE
    db.flush()
    return movement


def write_off_item(
    db: Session,
    *,
    item: Item,
    actor: Optional[User] = None,
    comment: Optional[str] = None,
) -> Movement:
    """Write an item off. Anything nested inside it stays nested and is not touched."""
    return move_item(
        db,
        item=item,
        to=LocationRef.written_off(),
        reason=MovementReason.WRITE_OFF,
        actor=actor,
        comment=comment,
    )


def history(db: Session, item: Item) -> list[Movement]:
    return list(
        db.scalars(
            select(Movement)
            .where(Movement.item_id == item.id)
            .order_by(Movement.moved_at.desc(), Movement.id.desc())
        )
    )


def open_issue(db: Session, item: Item) -> Optional[Movement]:
    """The issue record this item is still out on, if any."""
    if item.loc_kind is not LocationKind.PERSON:
        return None
    return db.scalars(
        select(Movement)
        .where(
            Movement.item_id == item.id,
            Movement.reason == MovementReason.ISSUE,
            Movement.returned_at.is_(None),
        )
        .order_by(Movement.moved_at.desc(), Movement.id.desc())
        .limit(1)
    ).first()


# --- internals ---------------------------------------------------------------


def _validate(db: Session, item: Item, ref: LocationRef) -> None:
    if ref.kind is LocationKind.INSIDE:
        if ref.parent_item_id is None:
            raise MoveError("Не выбрана единица, внутрь которой перемещаем.")
        container = db.get(Item, ref.parent_item_id)
        if container is None:
            raise MoveError("Единица-контейнер не найдена.")
        if container.id == item.id:
            raise MoveError("Единица не может находиться внутри самой себя.")
        if not container.type.is_container:
            raise MoveError(
                f"Тип «{container.type.name}» не может содержать вложенные единицы."
            )
        if container.is_written_off:
            raise MoveError(f"Единица {container.inv_number} списана.")
        if item.id is not None and tree.is_inside(db, container, item):
            raise MoveError(
                f"Нельзя вложить {item.inv_number} в {container.inv_number}: "
                "получится циклическая вложенность."
            )

    elif ref.kind is LocationKind.STORAGE:
        if db.get(StoragePlace, ref.storage_place_id) is None:
            raise MoveError("Место хранения не найдено.")

    elif ref.kind is LocationKind.PERSON:
        employee = db.get(Employee, ref.employee_id) if ref.employee_id else None
        if employee is None:
            raise MoveError("Сотрудник не найден.")
        if not employee.is_active:
            raise MoveError("Сотрудник уволен, выдача невозможна.")
        if ref.room_id is not None and db.get(Room, ref.room_id) is None:
            raise MoveError("Кабинет не найден.")

    elif ref.kind is LocationKind.ROOM:
        if db.get(Room, ref.room_id) is None:
            raise MoveError("Кабинет не найден.")

    elif ref.kind is LocationKind.EXTERNAL:
        if not (ref.external_note or "").strip():
            raise MoveError("Укажите, куда и кому передана единица.")


def _apply(item: Item, ref: LocationRef) -> None:
    room_id = ref.room_id
    if ref.kind is not LocationKind.PERSON and ref.kind is not LocationKind.ROOM:
        room_id = None
    item.loc_kind = ref.kind
    item.loc_parent_item_id = ref.parent_item_id if ref.kind is LocationKind.INSIDE else None
    item.loc_storage_place_id = (
        ref.storage_place_id if ref.kind is LocationKind.STORAGE else None
    )
    item.loc_employee_id = ref.employee_id if ref.kind is LocationKind.PERSON else None
    item.loc_room_id = room_id
    item.loc_external_note = ref.external_note if ref.kind is LocationKind.EXTERNAL else None
    item.loc_since = now()


def _build_movement(
    db: Session,
    *,
    item: Item,
    origin: Optional[LocationRef],
    target: LocationRef,
    reason: MovementReason,
    actor: Optional[User],
    recipient_employee_id: Optional[int] = None,
    expected_return_date: Optional[date] = None,
    comment: Optional[str] = None,
    moved_at: Optional[datetime] = None,
) -> Movement:
    movement = Movement(
        item_id=item.id,
        moved_at=moved_at or now(),
        reason=reason,
        comment=(comment or "").strip() or None,
        moved_by_user_id=actor.id if actor else None,
        recipient_employee_id=recipient_employee_id,
        expected_return_date=expected_return_date,
        to_kind=target.kind,
        to_parent_item_id=target.parent_item_id,
        to_storage_place_id=target.storage_place_id,
        to_employee_id=target.employee_id,
        to_room_id=target.room_id,
        to_external_note=target.external_note,
        to_label=describe_location(db, target),
    )
    if origin is not None:
        movement.from_kind = origin.kind
        movement.from_parent_item_id = origin.parent_item_id
        movement.from_storage_place_id = origin.storage_place_id
        movement.from_employee_id = origin.employee_id
        movement.from_room_id = origin.room_id
        movement.from_external_note = origin.external_note
        movement.from_label = describe_location(db, origin)
    return movement


def _close_open_issue(db: Session, item: Item, returned_at: datetime) -> None:
    issue = open_issue(db, item)
    if issue is not None:
        issue.returned_at = returned_at
