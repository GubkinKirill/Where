"""Makes the movement log impossible to bypass.

Item placement columns may only change inside `location_write()`, which is used
solely by `services.movements`. Any other code touching them — a router, a script,
a future contributor in a hurry — fails loudly at flush time.
"""

from contextlib import contextmanager

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models.item import LOCATION_COLUMNS, Item
from app.services.errors import LocationWriteError

_FLAG = "location_write_allowed"


@contextmanager
def location_write(db: Session):
    previous = db.info.get(_FLAG, False)
    db.info[_FLAG] = True
    try:
        yield
    finally:
        db.info[_FLAG] = previous


@event.listens_for(Session, "before_flush")
def _reject_direct_location_writes(session: Session, flush_context, instances) -> None:
    if session.info.get(_FLAG):
        return

    for obj in session.new:
        if isinstance(obj, Item):
            raise LocationWriteError(
                "New items must be created through services.items.create_item(), "
                "so that the first movement record is written."
            )

    for obj in session.dirty:
        if not isinstance(obj, Item):
            continue
        state = inspect(obj)
        changed = [
            column for column in LOCATION_COLUMNS if state.attrs[column].history.has_changes()
        ]
        if changed:
            raise LocationWriteError(
                f"Item {obj.inv_number}: placement columns {', '.join(changed)} were changed "
                "outside services.movements.move_item()."
            )
