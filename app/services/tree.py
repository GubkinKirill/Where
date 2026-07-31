from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import LocationKind
from app.models.item import Item

# a nesting chain deeper than this means the data is broken; bail out instead of looping
MAX_DEPTH = 20


def ancestors(db: Session, item: Item) -> list[Item]:
    """From the direct container upwards."""
    chain: list[Item] = []
    current = item
    for _ in range(MAX_DEPTH):
        if current.loc_kind is not LocationKind.INSIDE or current.loc_parent_item_id is None:
            break
        parent = db.get(Item, current.loc_parent_item_id)
        if parent is None:
            break
        chain.append(parent)
        current = parent
    return chain


def is_inside(db: Session, candidate: Item, container: Item) -> bool:
    """Is `candidate` somewhere inside `container`, at any depth?"""
    return any(parent.id == container.id for parent in ancestors(db, candidate))


def contents(db: Session, item: Item) -> list[Item]:
    return list(
        db.scalars(
            select(Item)
            .where(Item.loc_parent_item_id == item.id, Item.loc_kind == LocationKind.INSIDE)
            .order_by(Item.inv_number)
        )
    )
