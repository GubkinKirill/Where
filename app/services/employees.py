from typing import Optional

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.directory import Employee
from app.models.enums import LocationKind
from app.models.item import Item
from app.models.movement import Movement
from app.models.user import User
from app.services.errors import ServiceError
from app.services.movements import issue_item, return_to_storage


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


@dataclass(frozen=True)
class EmployeeLine:
    """A person plus how much is on them — the colleagues list and nothing more."""

    employee: Employee
    count: int


def with_counts(db: Session, *, query: Optional[str] = None) -> list[EmployeeLine]:
    """Active people and how many units each holds, in one pass over the items."""
    counts = dict(
        db.execute(
            select(Item.loc_employee_id, func.count(Item.id))
            .where(Item.loc_kind == LocationKind.PERSON)
            .group_by(Item.loc_employee_id)
        ).all()
    )
    stmt = select(Employee).where(Employee.is_active)
    if query:
        pattern = f"%{query}%"
        stmt = stmt.where(
            or_(Employee.full_name.ilike(pattern), Employee.position.ilike(pattern))
        )
    return [
        EmployeeLine(employee=employee, count=counts.get(employee.id, 0))
        for employee in db.scalars(stmt.order_by(Employee.full_name))
    ]


def history_of(db: Session, employee: Employee) -> list[Movement]:
    """Everything handed to this person or taken back from them, newest first."""
    return list(
        db.scalars(
            select(Movement)
            .where(
                or_(
                    Movement.to_employee_id == employee.id,
                    Movement.from_employee_id == employee.id,
                    Movement.recipient_employee_id == employee.id,
                )
            )
            .order_by(Movement.moved_at.desc(), Movement.id.desc())
            .limit(200)
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


def return_all_to_storage(
    db: Session,
    *,
    employee: Employee,
    storage_place_id: Optional[int],
    actor: Optional[User] = None,
    comment: Optional[str] = None,
) -> list[Movement]:
    """Take everything one person holds back onto a shelf — the usual end of a
    dismissal, when the equipment goes to the store rather than to a successor.
    One log record per unit, exactly as if each had been returned by hand."""
    if storage_place_id is None:
        raise ServiceError("Выберите место хранения, куда принимаете технику.")

    note = comment or f"Возврат от {employee.short_name}"
    return [
        return_to_storage(
            db,
            item=item,
            storage_place_id=storage_place_id,
            actor=actor,
            comment=note,
        )
        for item in items_of(db, employee)
    ]


def set_active(db: Session, *, employee: Employee, is_active: bool) -> Employee:
    """Dismissal does not touch the equipment: it stays on the person until moved,
    so nothing silently disappears from the books."""
    employee.is_active = is_active
    db.flush()
    return employee
