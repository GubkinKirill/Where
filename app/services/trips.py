"""Business trips: who left, where to, and what went with them.

Everything a trip does to a unit is an ordinary move through `move_item()` — the
journal is the same journal, and a trip is simply one more kind of place a thing
can be. What this module adds on top is the arithmetic of a trip: what left with
it, what came back, what stayed on site, and the rule that a trip does not close
while anything is still unaccounted for.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import now
from app.models.directory import Employee
from app.models.enums import ItemStatus, LocationKind, MovementReason, TripStatus
from app.models.item import Item
from app.models.movement import Movement
from app.models.trip import Trip
from app.models.user import User
from app.services.errors import ServiceError
from app.services.location import LocationRef
from app.services.movements import move_item
from app.services.numbering import next_inv_number

TRIP_PREFIX = "TRIP"


def get_trip(db: Session, trip_id: int) -> Optional[Trip]:
    return db.get(Trip, trip_id)


def create_trip(
    db: Session,
    *,
    employee: Employee,
    destination: str,
    departs_on: date,
    returns_on: Optional[date] = None,
    purpose: Optional[str] = None,
    project_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> Trip:
    destination = (destination or "").strip()
    if not destination:
        raise ServiceError("Укажите, куда едет сотрудник.")
    if not employee.is_active:
        raise ServiceError("Сотрудник уволен, командировку на него не оформить.")
    if returns_on is not None and returns_on < departs_on:
        raise ServiceError("Дата возвращения раньше даты выезда.")

    trip = Trip(
        code=next_inv_number(db, TRIP_PREFIX),
        employee_id=employee.id,
        destination=destination,
        purpose=(purpose or "").strip() or None,
        project_id=project_id,
        departs_on=departs_on,
        returns_on=returns_on,
        notes=(notes or "").strip() or None,
    )
    db.add(trip)
    db.flush()
    return trip


def update_trip(
    db: Session,
    *,
    trip: Trip,
    destination: str,
    departs_on: date,
    returns_on: Optional[date] = None,
    purpose: Optional[str] = None,
    project_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> Trip:
    """Dates and destination are paperwork, not placement: they stay editable."""
    destination = (destination or "").strip()
    if not destination:
        raise ServiceError("Укажите, куда едет сотрудник.")
    if returns_on is not None and returns_on < departs_on:
        raise ServiceError("Дата возвращения раньше даты выезда.")

    trip.destination = destination
    trip.departs_on = departs_on
    trip.returns_on = returns_on
    trip.purpose = (purpose or "").strip() or None
    trip.project_id = project_id
    trip.notes = (notes or "").strip() or None
    db.flush()
    return trip


def take_items(
    db: Session,
    *,
    trip: Trip,
    items: Iterable[Item],
    actor: Optional[User] = None,
    comment: Optional[str] = None,
    moved_at: Optional[datetime] = None,
) -> list[Movement]:
    """The suitcase is packed: every unit gets its own record in the journal."""
    _require_open(trip)
    chosen = list(items)
    if not chosen:
        raise ServiceError("Не выбрано ни одной единицы.")

    note = comment or f"Командировка {trip.code}: {trip.destination}"
    departed = moved_at or _departure_time(trip)
    moved = []
    for item in chosen:
        _check_can_travel(item, trip)
        moved.append(
            move_item(
                db,
                item=item,
                to=LocationRef.trip(trip.id),
                reason=MovementReason.TRIP_OUT,
                actor=actor,
                comment=note,
                moved_at=departed,
            )
        )
    return moved


def return_item(
    db: Session,
    *,
    trip: Trip,
    item: Item,
    to: LocationRef,
    actor: Optional[User] = None,
    comment: Optional[str] = None,
    moved_at: Optional[datetime] = None,
) -> Movement:
    """Came back with the traveller: onto a shelf, to a room, or straight to a person."""
    _require_in_trip(item, trip)
    if to.kind in (LocationKind.TRIP, LocationKind.WRITTEN_OFF, LocationKind.INSIDE):
        raise ServiceError("Из командировки принимают на склад, в кабинет или сотруднику.")

    movement = move_item(
        db,
        item=item,
        to=to,
        reason=MovementReason.TRIP_RETURN,
        actor=actor,
        recipient_employee_id=to.employee_id,
        comment=comment or f"Возврат из командировки {trip.code}",
        moved_at=moved_at,
    )
    if to.kind is LocationKind.PERSON:
        if item.status is ItemStatus.RESERVE:
            item.status = ItemStatus.IN_USE
    elif item.status is ItemStatus.IN_USE:
        item.status = ItemStatus.RESERVE
    db.flush()
    return movement


def leave_item(
    db: Session,
    *,
    trip: Trip,
    item: Item,
    note: Optional[str] = None,
    actor: Optional[User] = None,
    comment: Optional[str] = None,
    moved_at: Optional[datetime] = None,
) -> Movement:
    """Stayed on site: it is out of the department's hands but still on the books."""
    _require_in_trip(item, trip)
    where = (note or "").strip() or trip.destination
    return move_item(
        db,
        item=item,
        to=LocationRef.external(f"{where} (командировка {trip.code})"),
        reason=MovementReason.TRIP_LEFT,
        actor=actor,
        comment=comment or f"Оставлено на месте командировки {trip.code}",
        moved_at=moved_at,
    )


def items_in_trip(db: Session, trip: Trip) -> list[Item]:
    """What is with the traveller right now."""
    return list(
        db.scalars(
            select(Item)
            .where(Item.loc_kind == LocationKind.TRIP, Item.loc_trip_id == trip.id)
            .order_by(Item.inv_number)
        )
    )


@dataclass(frozen=True)
class TripLine:
    """One unit that left with the trip and what became of it."""

    item: Item
    taken_at: datetime
    outcome: str  # away | returned | left | written_off
    resolved_at: Optional[datetime] = None
    resolved_label: str = ""

    @property
    def is_away(self) -> bool:
        return self.outcome == "away"


def lines(db: Session, trip: Trip) -> list[TripLine]:
    """Everything the trip ever carried, each with its fate. Read from the journal,
    so a unit moved out by an ordinary move is counted as resolved too."""
    taken: dict[int, Movement] = {}
    for movement in db.scalars(
        select(Movement)
        .where(Movement.to_trip_id == trip.id)
        .order_by(Movement.moved_at, Movement.id)
    ):
        taken[movement.item_id] = movement

    left: dict[int, Movement] = {}
    for movement in db.scalars(
        select(Movement)
        .where(Movement.from_trip_id == trip.id)
        .order_by(Movement.moved_at, Movement.id)
    ):
        left[movement.item_id] = movement

    result = []
    for item_id, departure in taken.items():
        item = db.get(Item, item_id)
        if item is None:  # deleted without a trace, as only an admin can
            continue
        back = left.get(item_id)
        if item.loc_kind is LocationKind.TRIP and item.loc_trip_id == trip.id:
            result.append(TripLine(item=item, taken_at=departure.moved_at, outcome="away"))
        elif back is None:
            # moved out by something that did not record the trip side; still resolved
            result.append(
                TripLine(
                    item=item,
                    taken_at=departure.moved_at,
                    outcome="returned",
                    resolved_at=item.loc_since,
                )
            )
        else:
            result.append(
                TripLine(
                    item=item,
                    taken_at=departure.moved_at,
                    outcome=_outcome_of(back),
                    resolved_at=back.moved_at,
                    resolved_label=back.to_label,
                )
            )
    return sorted(result, key=lambda line: line.item.inv_number)


def close_trip(db: Session, *, trip: Trip) -> Trip:
    """A trip closes when nothing is left hanging: everything came back, stayed
    there on purpose, or was written off. Until then closing would lose things."""
    _require_open(trip)
    still_out = items_in_trip(db, trip)
    if still_out:
        numbers = ", ".join(item.inv_number for item in still_out[:5])
        tail = " и др." if len(still_out) > 5 else ""
        raise ServiceError(
            f"Не решена судьба {len(still_out)} ед.: {numbers}{tail}. "
            "По каждой отметьте возврат, «оставлено там» или списание."
        )
    trip.status = TripStatus.CLOSED
    trip.closed_at = now()
    db.flush()
    return trip


def reopen_trip(db: Session, *, trip: Trip) -> Trip:
    """Closed too early — somebody remembered a box still on site."""
    trip.status = TripStatus.OPEN
    trip.closed_at = None
    db.flush()
    return trip


def delete_trip(db: Session, *, trip: Trip) -> None:
    """Only a trip that never carried anything: the journal is not rewritable."""
    carried = db.scalars(
        select(Movement).where(
            (Movement.to_trip_id == trip.id) | (Movement.from_trip_id == trip.id)
        )
    ).first()
    if carried is not None:
        raise ServiceError(
            "С этой командировкой уже ездило оборудование — её нельзя удалить, "
            "только закрыть."
        )
    db.delete(trip)
    db.flush()


def list_trips(db: Session, *, include_closed: bool = False) -> list[Trip]:
    stmt = select(Trip)
    if not include_closed:
        stmt = stmt.where(Trip.status == TripStatus.OPEN)
    return list(db.scalars(stmt.order_by(Trip.status, Trip.departs_on.desc(), Trip.id.desc())))


def open_trips(db: Session) -> list[Trip]:
    return list(
        db.scalars(
            select(Trip).where(Trip.status == TripStatus.OPEN).order_by(Trip.departs_on)
        )
    )


def open_trips_of(db: Session, employee: Employee) -> list[Trip]:
    return list(
        db.scalars(
            select(Trip)
            .where(Trip.employee_id == employee.id, Trip.status == TripStatus.OPEN)
            .order_by(Trip.departs_on)
        )
    )


def items_away_with(db: Session, employee: Employee) -> list[Item]:
    """What this person has with them on the road — not «assigned», but theirs to
    bring back. Shown in their card and in their own cabinet."""
    return list(
        db.scalars(
            select(Item)
            .join(Trip, Item.loc_trip_id == Trip.id)
            .where(
                Item.loc_kind == LocationKind.TRIP,
                Trip.employee_id == employee.id,
                Trip.status == TripStatus.OPEN,
            )
            .order_by(Item.inv_number)
        )
    )


def overdue_trips(db: Session, today: Optional[date] = None) -> list[Trip]:
    """Should have been back by now, and something is still out there."""
    today = today or date.today()
    late = db.scalars(
        select(Trip)
        .where(
            Trip.status == TripStatus.OPEN,
            Trip.returns_on.is_not(None),
            Trip.returns_on < today,
        )
        .order_by(Trip.returns_on)
    )
    return [trip for trip in late if items_in_trip(db, trip)]


def candidates(db: Session, trip: Trip) -> list[Item]:
    """What can be packed: anything on the books that is not already travelling and
    not nested inside something else — nested parts travel with their container."""
    return list(
        db.scalars(
            select(Item)
            .where(
                Item.status != ItemStatus.WRITTEN_OFF,
                Item.loc_kind.not_in((LocationKind.TRIP, LocationKind.INSIDE)),
            )
            .order_by(Item.inv_number)
        )
    )


def count_away(db: Session) -> int:
    return db.scalar(
        select(func.count(Item.id)).where(Item.loc_kind == LocationKind.TRIP)
    ) or 0


# --- internals ---------------------------------------------------------------


def _require_open(trip: Trip) -> None:
    if not trip.is_open:
        raise ServiceError(f"Командировка {trip.code} закрыта.")


def _require_in_trip(item: Item, trip: Trip) -> None:
    if item.loc_kind is not LocationKind.TRIP or item.loc_trip_id != trip.id:
        raise ServiceError(
            f"Единица {item.inv_number} не числится в командировке {trip.code}."
        )


def _check_can_travel(item: Item, trip: Trip) -> None:
    if item.loc_kind is LocationKind.TRIP:
        raise ServiceError(
            f"Единица {item.inv_number} уже в командировке. "
            "Сначала примите её обратно."
        )
    if item.loc_kind is LocationKind.INSIDE:
        raise ServiceError(
            f"Единица {item.inv_number} вложена в другую и едет вместе с ней. "
            "Возьмите в командировку контейнер или сначала изымите её из состава."
        )


def _departure_time(trip: Trip) -> datetime:
    """Things leave when the trip leaves. A trip written down after the fact keeps
    the real date in the journal, not the minute somebody got round to typing it."""
    if trip.departs_on >= date.today():
        return now()
    return datetime.combine(trip.departs_on, time(9, 0))


def _outcome_of(movement: Movement) -> str:
    if movement.reason is MovementReason.TRIP_LEFT:
        return "left"
    if movement.reason is MovementReason.WRITE_OFF:
        return "written_off"
    return "returned"
