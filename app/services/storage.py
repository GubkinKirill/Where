"""«Что лежит на складе» — the two kinds of accounting shown side by side:
numbered units on a shelf and consumable positions kept on the same shelf.
"""

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.consumable import ConsumableStock
from app.models.directory import StoragePlace
from app.models.enums import LocationKind
from app.models.item import Item


@dataclass
class PlaceLine:
    """A place with what is on it, and the totals of everything nested below."""

    place: StoragePlace
    items: int = 0
    positions: int = 0
    children: list["PlaceLine"] = field(default_factory=list)

    @property
    def total_items(self) -> int:
        return self.items + sum(child.total_items for child in self.children)

    @property
    def total_positions(self) -> int:
        return self.positions + sum(child.total_positions for child in self.children)

    @property
    def is_empty(self) -> bool:
        return self.total_items == 0 and self.total_positions == 0


def tree(db: Session) -> list[PlaceLine]:
    """Cabinets with their shelves and cells, each carrying its own counts."""
    item_counts = dict(
        db.execute(
            select(Item.loc_storage_place_id, func.count(Item.id))
            .where(Item.loc_kind == LocationKind.STORAGE)
            .group_by(Item.loc_storage_place_id)
        ).all()
    )
    position_counts = dict(
        db.execute(
            select(ConsumableStock.storage_place_id, func.count(ConsumableStock.id))
            .where(ConsumableStock.is_active)
            .group_by(ConsumableStock.storage_place_id)
        ).all()
    )

    lines = {
        place.id: PlaceLine(
            place=place,
            items=item_counts.get(place.id, 0),
            positions=position_counts.get(place.id, 0),
        )
        for place in db.scalars(select(StoragePlace).order_by(StoragePlace.name))
    }

    roots: list[PlaceLine] = []
    for line in lines.values():
        parent = lines.get(line.place.parent_id) if line.place.parent_id else None
        if parent is None:
            roots.append(line)
        else:
            parent.children.append(line)
    return roots


def items_on(db: Session, place: StoragePlace) -> list[Item]:
    return list(
        db.scalars(
            select(Item)
            .where(
                Item.loc_kind == LocationKind.STORAGE,
                Item.loc_storage_place_id == place.id,
            )
            .order_by(Item.inv_number)
        )
    )


def get_place(db: Session, place_id: int) -> Optional[StoragePlace]:
    return db.get(StoragePlace, place_id)


def children_of(db: Session, place: StoragePlace) -> list[StoragePlace]:
    return list(
        db.scalars(
            select(StoragePlace)
            .where(StoragePlace.parent_id == place.id)
            .order_by(StoragePlace.name)
        )
    )
