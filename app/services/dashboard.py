"""Numbers for the front page. One query per figure, nothing cached: at this size
the whole table fits in memory and a stale figure would cost more than the scan."""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import ItemStatus, LocationKind, MovementReason
from app.models.item import Item
from app.models.movement import Movement
from app.services import consumables as consumables_service
from app.services import projects as projects_service
from app.services import requests as requests_service
from app.services import trips as trips_service


@dataclass(frozen=True)
class Tile:
    label: str
    value: int
    url: str
    hint: str = ""
    tone: str = ""  # "" | "warn"


def summary(db: Session) -> dict:
    by_location = dict(
        db.execute(
            select(Item.loc_kind, func.count(Item.id))
            .where(Item.status != ItemStatus.WRITTEN_OFF)
            .group_by(Item.loc_kind)
        ).all()
    )
    by_status = dict(
        db.execute(select(Item.status, func.count(Item.id)).group_by(Item.status)).all()
    )
    total = sum(by_status.values())
    overdue = _overdue(db)
    unconfirmed = _unconfirmed_count(db)
    open_requests = requests_service.open_count(db)
    low_stock = consumables_service.low_stock(db)
    late_trips = trips_service.overdue_trips(db)
    open_trips = trips_service.open_trips(db)

    tiles = [
        Tile("Всего на учёте", total - by_status.get(ItemStatus.WRITTEN_OFF, 0), "/items",
             "не считая списанные"),
        Tile("У сотрудников", by_location.get(LocationKind.PERSON, 0),
             f"/items?loc_kind={LocationKind.PERSON.value}"),
        Tile("На складе", by_location.get(LocationKind.STORAGE, 0),
             f"/items?loc_kind={LocationKind.STORAGE.value}"),
        Tile("В кабинетах", by_location.get(LocationKind.ROOM, 0),
             f"/items?loc_kind={LocationKind.ROOM.value}"),
        Tile("В командировках", by_location.get(LocationKind.TRIP, 0), "/trips",
             f"открытых поездок: {len(open_trips)}" if open_trips else "поездок нет"),
        Tile("В составе других", by_location.get(LocationKind.INSIDE, 0),
             f"/items?loc_kind={LocationKind.INSIDE.value}"),
        Tile("Из проектов", projects_service.project_owned_count(db), "/projects",
             "числится не за предприятием"),
        Tile("В ремонте", by_status.get(ItemStatus.REPAIR, 0),
             f"/items?status={ItemStatus.REPAIR.value}",
             tone="warn" if by_status.get(ItemStatus.REPAIR) else ""),
    ]

    attention = [
        Tile("Не подтверждена выдача", unconfirmed, "/reports/unconfirmed",
             "сотрудник ещё не нажал «Получил»", tone="warn" if unconfirmed else ""),
        Tile("Просрочен возврат", len(overdue), "/reports/overdue",
             "срок возврата прошёл", tone="warn" if overdue else ""),
        Tile("Не вернулись из поездки", len(late_trips), "/trips",
             "срок командировки прошёл, вещи ещё там",
             tone="warn" if late_trips else ""),
        Tile("Открытых заявок", open_requests, "/requests", "от сотрудников",
             tone="warn" if open_requests else ""),
        Tile("Заканчивается на складе", len(low_stock), "/reports/low-stock",
             "расходники ниже порога", tone="warn" if low_stock else ""),
    ]

    return {
        "tiles": tiles,
        "low_stock": low_stock,
        "attention": attention,
        "overdue": overdue,
        "trips": open_trips,
        "late_trips": late_trips,
        "recent": recent_movements(db),
        "by_status": by_status,
        "total": total,
    }


def overdue_issues(db: Session) -> list[Movement]:
    return _overdue(db)


def recent_movements(db: Session, limit: int = 12) -> list[Movement]:
    return list(
        db.scalars(
            select(Movement)
            .order_by(Movement.moved_at.desc(), Movement.id.desc())
            .limit(limit)
        )
    )


# --- internals ---------------------------------------------------------------


def _overdue(db: Session, today: Optional[date] = None) -> list[Movement]:
    today = today or date.today()
    return list(
        db.scalars(
            select(Movement)
            .where(
                Movement.reason == MovementReason.ISSUE,
                Movement.returned_at.is_(None),
                Movement.expected_return_date.is_not(None),
                Movement.expected_return_date < today,
            )
            .order_by(Movement.expected_return_date)
        )
    )


def _unconfirmed_count(db: Session) -> int:
    return db.scalar(
        select(func.count(Movement.id)).where(
            Movement.reason == MovementReason.ISSUE,
            Movement.returned_at.is_(None),
            Movement.acknowledged_at.is_(None),
        )
    ) or 0
