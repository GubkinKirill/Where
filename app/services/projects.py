"""Equipment grouped by whose it is.

A project owns units the way a shelf never can: the tie survives every move, so
the question «what came with this project and where is it now» has one answer even
when the kit is on a shelf, the antenna is in a trip and the laptop is on a desk.

Belonging is a plain column on Item — `services.items` writes it with the rest of
the form. Nothing here touches placement.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import ItemStatus, LocationKind, ProjectStatus
from app.models.item import Item
from app.models.project import Project
from app.models.trip import Trip


def get_project(db: Session, project_id: int) -> Optional[Project]:
    return db.get(Project, project_id)


def get_by_code(db: Session, code: str) -> Optional[Project]:
    return db.scalars(select(Project).where(Project.code == code.strip())).first()


def list_projects(db: Session, *, include_closed: bool = True) -> list[Project]:
    stmt = select(Project)
    if not include_closed:
        stmt = stmt.where(Project.status != ProjectStatus.CLOSED)
    return list(db.scalars(stmt.order_by(Project.status, Project.code)))


def items_of(
    db: Session, project: Project, *, include_written_off: bool = False
) -> list[Item]:
    stmt = select(Item).where(Item.project_id == project.id)
    if not include_written_off:
        stmt = stmt.where(Item.status != ItemStatus.WRITTEN_OFF)
    return list(db.scalars(stmt.order_by(Item.inv_number)))


def item_counts(db: Session) -> dict[Optional[int], int]:
    """How many live units each project holds; the None key is the enterprise itself."""
    return dict(
        db.execute(
            select(Item.project_id, func.count(Item.id))
            .where(Item.status != ItemStatus.WRITTEN_OFF)
            .group_by(Item.project_id)
        ).all()
    )


def trips_of(db: Session, project: Project) -> list[Trip]:
    return list(
        db.scalars(
            select(Trip)
            .where(Trip.project_id == project.id)
            .order_by(Trip.departs_on.desc(), Trip.id.desc())
        )
    )


@dataclass(frozen=True)
class ProjectSummary:
    """The project card in numbers: how much, and how it is spread around."""

    project: Project
    items: list[Item]
    by_location: dict[LocationKind, int]
    written_off: int

    @property
    def total(self) -> int:
        return len(self.items)


def summary(db: Session, project: Project) -> ProjectSummary:
    items = items_of(db, project)
    by_location: dict[LocationKind, int] = {}
    for item in items:
        by_location[item.loc_kind] = by_location.get(item.loc_kind, 0) + 1
    written_off = (
        db.scalar(
            select(func.count(Item.id)).where(
                Item.project_id == project.id,
                Item.status == ItemStatus.WRITTEN_OFF,
            )
        )
        or 0
    )
    return ProjectSummary(
        project=project,
        items=items,
        by_location=by_location,
        written_off=written_off,
    )


def company_owned_count(db: Session) -> int:
    """Units on the books of the enterprise — the ones with no project behind them."""
    return (
        db.scalar(
            select(func.count(Item.id)).where(
                Item.project_id.is_(None), Item.status != ItemStatus.WRITTEN_OFF
            )
        )
        or 0
    )


def project_owned_count(db: Session) -> int:
    return (
        db.scalar(
            select(func.count(Item.id)).where(
                Item.project_id.is_not(None), Item.status != ItemStatus.WRITTEN_OFF
            )
        )
        or 0
    )
