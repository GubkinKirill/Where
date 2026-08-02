"""Kits: a container item checked against a template of what it must contain.

Nothing new happens to placement here — a kit is an ordinary container and its
parts are nested inside it. The template only answers "what is still missing".
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ItemStatus, LocationKind
from app.models.item import Item, ItemType
from app.models.kit import KitTemplate
from app.services import tree

# how many suitable spares to suggest per missing position
SPARES_SHOWN = 5


@dataclass
class LineStatus:
    item_type: ItemType
    required: int
    present: int
    note: Optional[str]
    spares: list[Item]

    @property
    def missing(self) -> int:
        return max(0, self.required - self.present)

    @property
    def extra(self) -> int:
        return max(0, self.present - self.required)

    @property
    def is_satisfied(self) -> bool:
        return self.present >= self.required


@dataclass
class KitStatus:
    item: Item
    template: KitTemplate
    lines: list[LineStatus]
    unexpected: list[Item]

    @property
    def missing_total(self) -> int:
        return sum(line.missing for line in self.lines)

    @property
    def is_complete(self) -> bool:
        return self.missing_total == 0

    @property
    def required_total(self) -> int:
        return sum(line.required for line in self.lines)

    @property
    def present_total(self) -> int:
        return sum(min(line.present, line.required) for line in self.lines)


def status(db: Session, kit: Item) -> Optional[KitStatus]:
    """Compare what is inside the kit with what the template asks for."""
    if kit.kit_template is None:
        return None

    contents = tree.contents(db, kit)
    counted: dict[int, int] = {}
    for child in contents:
        counted[child.type_id] = counted.get(child.type_id, 0) + 1

    lines = []
    for line in kit.kit_template.lines:
        present = counted.get(line.item_type_id, 0)
        missing = max(0, line.quantity - present)
        lines.append(
            LineStatus(
                item_type=line.item_type,
                required=line.quantity,
                present=present,
                note=line.note,
                spares=spares_for(db, line.item_type_id) if missing else [],
            )
        )

    expected_types = {line.item_type_id for line in kit.kit_template.lines}
    unexpected = [child for child in contents if child.type_id not in expected_types]
    return KitStatus(item=kit, template=kit.kit_template, lines=lines, unexpected=unexpected)


def spares_for(db: Session, item_type_id: int) -> list[Item]:
    """Units of that type lying in storage and ready to be put into a kit."""
    return list(
        db.scalars(
            select(Item)
            .where(
                Item.type_id == item_type_id,
                Item.loc_kind == LocationKind.STORAGE,
                Item.status.in_([ItemStatus.RESERVE, ItemStatus.IN_USE]),
            )
            .order_by(Item.inv_number)
            .limit(SPARES_SHOWN)
        )
    )


def all_kits(db: Session) -> list[KitStatus]:
    """Every item assembled to a template, incomplete ones first."""
    kits = db.scalars(
        select(Item)
        .where(Item.kit_template_id.is_not(None), Item.status != ItemStatus.WRITTEN_OFF)
        .order_by(Item.inv_number)
    )
    statuses = [status(db, kit) for kit in kits]
    return sorted(
        [value for value in statuses if value is not None],
        key=lambda value: (value.is_complete, value.item.inv_number),
    )


def templates(db: Session, *, only_active: bool = False) -> list[KitTemplate]:
    stmt = select(KitTemplate).order_by(KitTemplate.name)
    if only_active:
        stmt = stmt.where(KitTemplate.is_active)
    return list(db.scalars(stmt))
