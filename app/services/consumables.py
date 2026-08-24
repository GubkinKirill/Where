"""Quantity accounting for consumables: receipts, issues, recount corrections.

Every change is a line in the ledger; `ConsumableStock.quantity` is a cache this
module keeps in step. Nothing else may write it — see stock_guard.
"""

from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.consumable import ConsumableMovement, ConsumableStock
from app.models.directory import Employee
from app.models.enums import ConsumableReason
from app.models.user import User
from app.schemas.consumable import ConsumableFilter, ConsumableForm
from app.services.errors import ServiceError
from app.services.stock_guard import stock_write


def get_stock(db: Session, stock_id: int) -> Optional[ConsumableStock]:
    return db.get(ConsumableStock, stock_id)


def search(db: Session, filters: ConsumableFilter) -> list[ConsumableStock]:
    stmt = select(ConsumableStock)
    if filters.q:
        pattern = f"%{filters.q.strip()}%"
        stmt = stmt.where(
            or_(
                ConsumableStock.name.ilike(pattern),
                ConsumableStock.category.ilike(pattern),
                ConsumableStock.notes.ilike(pattern),
            )
        )
    if filters.category:
        stmt = stmt.where(ConsumableStock.category == filters.category)
    if filters.storage_place_id:
        stmt = stmt.where(ConsumableStock.storage_place_id == filters.storage_place_id)
    if not filters.include_inactive:
        stmt = stmt.where(ConsumableStock.is_active)

    found = list(db.scalars(stmt.order_by(ConsumableStock.category, ConsumableStock.name)))
    if filters.low_only:
        found = [stock for stock in found if stock.is_low or stock.is_out]
    return found


def categories(db: Session) -> list[str]:
    return [
        value
        for value in db.scalars(
            select(ConsumableStock.category)
            .where(ConsumableStock.category != "")
            .distinct()
            .order_by(ConsumableStock.category)
        )
    ]


def create_stock(
    db: Session,
    *,
    form: ConsumableForm,
    quantity: int = 0,
    actor: Optional[User] = None,
    comment: Optional[str] = None,
) -> ConsumableStock:
    """A new position starts at zero and gets its opening balance as a receipt,
    so even the first quantity has a line in the ledger."""
    stock = ConsumableStock()
    _apply_form(stock, form)
    with stock_write(db):
        stock.quantity = 0
        db.add(stock)
        db.flush()

    if quantity:
        receive(db, stock=stock, quantity=quantity, actor=actor, comment=comment or "Начальный остаток")
    return stock


def update_stock(db: Session, *, stock: ConsumableStock, form: ConsumableForm) -> ConsumableStock:
    """Everything about a position except its quantity — that only the ledger moves."""
    _apply_form(stock, form)
    db.flush()
    return stock


def receive(
    db: Session,
    *,
    stock: ConsumableStock,
    quantity: int,
    actor: Optional[User] = None,
    comment: Optional[str] = None,
) -> ConsumableMovement:
    if quantity <= 0:
        raise ServiceError("Количество прихода должно быть больше нуля.")
    return _record(
        db,
        stock=stock,
        delta=quantity,
        reason=ConsumableReason.RECEIPT,
        actor=actor,
        comment=comment,
    )


def issue(
    db: Session,
    *,
    stock: ConsumableStock,
    quantity: int,
    employee_id: Optional[int] = None,
    actor: Optional[User] = None,
    comment: Optional[str] = None,
) -> ConsumableMovement:
    """Hand consumables out. Who took them or what for is required: a minus in the
    ledger with nothing beside it is how stock quietly evaporates."""
    if quantity <= 0:
        raise ServiceError("Количество расхода должно быть больше нуля.")
    if quantity > stock.quantity:
        raise ServiceError(
            f"На складе только {stock.quantity} {stock.unit} — списать больше нельзя. "
            "Если остаток неверен, сделайте корректировку после пересчёта."
        )
    if employee_id is None and not (comment or "").strip():
        raise ServiceError("Укажите, кому выдаёте или зачем списываете.")
    if employee_id is not None:
        employee = db.get(Employee, employee_id)
        if employee is None:
            raise ServiceError("Сотрудник не найден.")

    return _record(
        db,
        stock=stock,
        delta=-quantity,
        reason=ConsumableReason.ISSUE,
        employee_id=employee_id,
        actor=actor,
        comment=comment,
    )


def adjust(
    db: Session,
    *,
    stock: ConsumableStock,
    counted: int,
    actor: Optional[User] = None,
    comment: Optional[str] = None,
) -> ConsumableMovement:
    """After a recount: set what is actually on the shelf, log the difference."""
    if counted < 0:
        raise ServiceError("Остаток не может быть отрицательным.")
    delta = counted - stock.quantity
    if delta == 0:
        raise ServiceError("Остаток совпадает с учётным, корректировать нечего.")
    return _record(
        db,
        stock=stock,
        delta=delta,
        reason=ConsumableReason.ADJUST,
        actor=actor,
        comment=comment or "Пересчёт",
    )


def history(db: Session, stock: ConsumableStock) -> list[ConsumableMovement]:
    return list(
        db.scalars(
            select(ConsumableMovement)
            .where(ConsumableMovement.stock_id == stock.id)
            .order_by(ConsumableMovement.happened_at.desc(), ConsumableMovement.id.desc())
        )
    )


def issued_to(db: Session, employee: Employee, limit: int = 20) -> list[ConsumableMovement]:
    """What this person has been given from the shelf — mice, cables, adapters."""
    return list(
        db.scalars(
            select(ConsumableMovement)
            .where(
                ConsumableMovement.employee_id == employee.id,
                ConsumableMovement.reason == ConsumableReason.ISSUE,
            )
            .order_by(ConsumableMovement.happened_at.desc(), ConsumableMovement.id.desc())
            .limit(limit)
        )
    )


def low_stock(db: Session) -> list[ConsumableStock]:
    """Running out: at or below the threshold, and everything already at zero."""
    return [
        stock
        for stock in db.scalars(
            select(ConsumableStock)
            .where(ConsumableStock.is_active)
            .order_by(ConsumableStock.category, ConsumableStock.name)
        )
        if stock.is_low or stock.is_out
    ]


def low_stock_count(db: Session) -> int:
    return len(low_stock(db))


def total_positions(db: Session) -> int:
    return db.scalar(
        select(func.count(ConsumableStock.id)).where(ConsumableStock.is_active)
    ) or 0


def on_place(db: Session, storage_place_id: int) -> list[ConsumableStock]:
    return list(
        db.scalars(
            select(ConsumableStock)
            .where(
                ConsumableStock.storage_place_id == storage_place_id,
                ConsumableStock.is_active,
            )
            .order_by(ConsumableStock.category, ConsumableStock.name)
        )
    )


def delete_stock(db: Session, *, stock: ConsumableStock) -> None:
    """Only a position nothing ever happened to. A used one is deactivated instead,
    so its ledger stays readable."""
    if db.scalar(
        select(func.count(ConsumableMovement.id)).where(
            ConsumableMovement.stock_id == stock.id
        )
    ):
        raise ServiceError(
            "По позиции есть движения. Снимите флажок «в обороте» — история сохранится."
        )
    db.delete(stock)
    db.flush()


# --- internals ---------------------------------------------------------------


def _apply_form(stock: ConsumableStock, form: ConsumableForm) -> None:
    stock.name = form.name
    stock.category = form.category or ""
    stock.unit = form.unit or "шт."
    stock.min_quantity = form.min_quantity
    stock.storage_place_id = form.storage_place_id
    stock.notes = form.notes
    stock.is_active = form.is_active


def _record(
    db: Session,
    *,
    stock: ConsumableStock,
    delta: int,
    reason: ConsumableReason,
    employee_id: Optional[int] = None,
    actor: Optional[User] = None,
    comment: Optional[str] = None,
) -> ConsumableMovement:
    with stock_write(db):
        stock.quantity += delta
        movement = ConsumableMovement(
            stock_id=stock.id,
            reason=reason,
            delta=delta,
            quantity_after=stock.quantity,
            employee_id=employee_id,
            moved_by_user_id=actor.id if actor else None,
            comment=(comment or "").strip() or None,
        )
        db.add(movement)
        db.flush()
    return movement
