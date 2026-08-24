"""The consumable ledger, made impossible to bypass.

Same idea as location_guard: `ConsumableStock.quantity` may only change inside
`stock_write()`, which only `services.consumables` uses. Anything else — a router
in a hurry, a fixing script — fails at flush time instead of silently leaving the
quantity and the ledger disagreeing.
"""

from contextlib import contextmanager

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models.consumable import QUANTITY_COLUMN, ConsumableStock
from app.services.errors import LocationWriteError

_FLAG = "stock_write_allowed"


@contextmanager
def stock_write(db: Session):
    previous = db.info.get(_FLAG, False)
    db.info[_FLAG] = True
    try:
        yield
    finally:
        db.info[_FLAG] = previous


@event.listens_for(Session, "before_flush")
def _reject_direct_quantity_writes(session: Session, flush_context, instances) -> None:
    if session.info.get(_FLAG):
        return

    for obj in session.dirty:
        if not isinstance(obj, ConsumableStock):
            continue
        if inspect(obj).attrs[QUANTITY_COLUMN].history.has_changes():
            raise LocationWriteError(
                f"Consumable «{obj.name}»: quantity was changed outside "
                "services.consumables — the ledger would not match."
            )
