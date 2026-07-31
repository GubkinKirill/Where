from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.directory import Employee
from app.models.enums import LocationKind
from app.models.item import Item
from app.models.movement import Movement
from app.models.user import User
from app.services.errors import ServiceError
from app.services.movements import issue_item


def get_employee(db: Session, employee_id: int) -> Optional[Employee]:
    return db.get(Employee, employee_id)


def items_of(db: Session, employee: Employee) -> list[Item]:
    """What the person is holding right now, in the order it is easiest to check."""
    return list(
        db.scalars(
            select(Item)
            .where(
                Item.loc_kind == LocationKind.PERSON,
                Item.loc_employee_id == employee.id,
            )
            .order_by(Item.inv_number)
        )
    )


def transfer_items(
    db: Session,
    *,
    source: Employee,
    target: Employee,
    actor: Optional[User] = None,
    comment: Optional[str] = None,
) -> list[Movement]:
    """Hand everything one person holds over to another, one log record per item."""
    if target.id == source.id:
        raise ServiceError("Выберите другого сотрудника.")
    if not target.is_active:
        raise ServiceError("Нельзя передать технику уволенному сотруднику.")

    note = comment or f"Передано от {source.short_name}"
    return [
        issue_item(
            db,
            item=item,
            employee_id=target.id,
            room_id=target.default_room_id,
            actor=actor,
            comment=note,
        )
        for item in items_of(db, source)
    ]


def set_active(db: Session, *, employee: Employee, is_active: bool) -> Employee:
    """Dismissal does not touch the equipment: it stays on the person until moved,
    so nothing silently disappears from the books."""
    employee.is_active = is_active
    db.flush()
    return employee
