from sqlalchemy.orm import Session

from app.models.item import NumberSequence


def next_inv_number(db: Session, prefix: str) -> str:
    """PC-0014 and so on: type prefix plus a counter of its own.

    Numbers are never reused — the counter only goes up, writing an item off does
    not free its number. Two writers racing here would collide on the unique index
    of items.inv_number rather than silently share a number.
    """
    prefix = prefix.strip().upper()
    sequence = db.get(NumberSequence, prefix)
    if sequence is None:
        sequence = NumberSequence(prefix=prefix, last_value=0)
        db.add(sequence)
    sequence.last_value += 1
    db.flush()
    return f"{prefix}-{sequence.last_value:04d}"
