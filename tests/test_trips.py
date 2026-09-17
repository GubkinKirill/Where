"""Business trips: equipment leaves with a person and has to be accounted for."""

from datetime import date, timedelta

import pytest

from app.models.enums import ItemStatus, LocationKind, MovementReason, TripStatus
from app.models.trip import Trip
from app.services import movements as movements_service
from app.services import trips as trips_service
from app.services.errors import ServiceError
from app.services.location import LocationRef
from tests.factories import make_item


@pytest.fixture
def trip(db, employee) -> Trip:
    return trips_service.create_trip(
        db,
        employee=employee,
        destination="Новосибирск, площадка «Север»",
        departs_on=date.today(),
        returns_on=date.today() + timedelta(days=14),
        purpose="Монтаж базовой станции",
    )


def test_trip_gets_a_number_of_its_own(db, employee):
    first = trips_service.create_trip(
        db, employee=employee, destination="Омск", departs_on=date.today()
    )
    second = trips_service.create_trip(
        db, employee=employee, destination="Томск", departs_on=date.today()
    )

    assert first.code == "TRIP-0001"
    assert second.code == "TRIP-0002"
    assert first.status is TripStatus.OPEN


def test_return_date_before_departure_is_refused(db, employee):
    with pytest.raises(ServiceError):
        trips_service.create_trip(
            db,
            employee=employee,
            destination="Омск",
            departs_on=date.today(),
            returns_on=date.today() - timedelta(days=1),
        )


def test_taking_an_item_moves_it_into_the_trip(db, types, shelf, trip, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    trips_service.take_items(db, trip=trip, items=[item], actor=actor)

    assert item.loc_kind is LocationKind.TRIP
    assert item.loc_trip_id == trip.id
    assert item.loc_storage_place_id is None

    log = movements_service.history(db, item)
    assert log[0].reason is MovementReason.TRIP_OUT
    assert log[0].to_trip_id == trip.id
    assert log[0].to_label == "командировка · Новосибирск, площадка «Север», Петров И. С."


def test_issued_item_taken_on_a_trip_closes_its_handover(db, types, shelf, employee, trip, actor):
    """Otherwise it would hang in «not confirmed» and «overdue» for ever."""
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)
    assert movements_service.unacknowledged(db)

    trips_service.take_items(db, trip=trip, items=[item], actor=actor)

    assert movements_service.unacknowledged(db) == []


def test_an_item_cannot_travel_twice_at_once(db, types, shelf, employee, trip, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    other = trips_service.create_trip(
        db, employee=employee, destination="Омск", departs_on=date.today()
    )
    trips_service.take_items(db, trip=trip, items=[item], actor=actor)

    with pytest.raises(ServiceError, match="уже в командировке"):
        trips_service.take_items(db, trip=other, items=[item], actor=actor)


def test_nested_parts_travel_with_their_container(db, types, shelf, trip, actor):
    machine = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    stick = make_item(db, types["RAM"], at=LocationRef.inside(machine.id), actor=actor)

    with pytest.raises(ServiceError, match="вложена"):
        trips_service.take_items(db, trip=trip, items=[stick], actor=actor)

    trips_service.take_items(db, trip=trip, items=[machine], actor=actor)
    assert stick.loc_kind is LocationKind.INSIDE
    assert stick.loc_parent_item_id == machine.id


def test_returning_puts_it_back_and_is_logged(db, types, shelf, trip, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    trips_service.take_items(db, trip=trip, items=[item], actor=actor)

    trips_service.return_item(
        db, trip=trip, item=item, to=LocationRef.storage(shelf.id), actor=actor
    )

    assert item.loc_kind is LocationKind.STORAGE
    assert item.loc_trip_id is None
    log = movements_service.history(db, item)
    assert log[0].reason is MovementReason.TRIP_RETURN
    assert log[0].from_trip_id == trip.id


def test_returning_to_a_person_marks_it_in_use(db, types, shelf, employee, trip, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    trips_service.take_items(db, trip=trip, items=[item], actor=actor)

    trips_service.return_item(
        db, trip=trip, item=item, to=LocationRef.person(employee.id), actor=actor
    )

    assert item.loc_kind is LocationKind.PERSON
    assert item.status is ItemStatus.IN_USE


def test_left_on_site_stays_on_the_books(db, types, shelf, trip, actor):
    item = make_item(db, types["MON"], at=LocationRef.storage(shelf.id), actor=actor)
    trips_service.take_items(db, trip=trip, items=[item], actor=actor)

    trips_service.leave_item(db, trip=trip, item=item, note="Площадка «Север»", actor=actor)

    assert item.loc_kind is LocationKind.EXTERNAL
    assert trip.code in item.loc_external_note
    assert item.status is not ItemStatus.WRITTEN_OFF
    assert movements_service.history(db, item)[0].reason is MovementReason.TRIP_LEFT


def test_an_item_of_another_trip_cannot_be_returned_here(db, types, shelf, employee, trip, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    other = trips_service.create_trip(
        db, employee=employee, destination="Омск", departs_on=date.today()
    )
    trips_service.take_items(db, trip=trip, items=[item], actor=actor)

    with pytest.raises(ServiceError, match="не числится в командировке"):
        trips_service.return_item(
            db, trip=other, item=item, to=LocationRef.storage(shelf.id), actor=actor
        )


def test_trip_does_not_close_while_something_is_still_out(db, types, shelf, trip, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    trips_service.take_items(db, trip=trip, items=[item], actor=actor)

    with pytest.raises(ServiceError, match="Не решена судьба"):
        trips_service.close_trip(db, trip=trip)

    trips_service.return_item(
        db, trip=trip, item=item, to=LocationRef.storage(shelf.id), actor=actor
    )
    trips_service.close_trip(db, trip=trip)

    assert trip.status is TripStatus.CLOSED
    assert trip.closed_at is not None


def test_nothing_can_be_added_to_a_closed_trip(db, types, shelf, trip, actor):
    trips_service.close_trip(db, trip=trip)
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    with pytest.raises(ServiceError):
        trips_service.take_items(db, trip=trip, items=[item], actor=actor)


def test_lines_tell_what_became_of_everything(db, types, shelf, trip, actor):
    back = make_item(db, types["PC"], name="Вернётся", at=LocationRef.storage(shelf.id), actor=actor)
    stays = make_item(db, types["MON"], name="Останется", at=LocationRef.storage(shelf.id), actor=actor)
    away = make_item(db, types["RAM"], name="Ещё там", at=LocationRef.storage(shelf.id), actor=actor)
    trips_service.take_items(db, trip=trip, items=[back, stays, away], actor=actor)

    trips_service.return_item(db, trip=trip, item=back, to=LocationRef.storage(shelf.id), actor=actor)
    trips_service.leave_item(db, trip=trip, item=stays, actor=actor)

    outcomes = {line.item.name: line.outcome for line in trips_service.lines(db, trip)}
    assert outcomes == {"Вернётся": "returned", "Останется": "left", "Ещё там": "away"}


def test_written_off_on_site_counts_as_resolved(db, types, shelf, trip, actor):
    item = make_item(db, types["MON"], at=LocationRef.storage(shelf.id), actor=actor)
    trips_service.take_items(db, trip=trip, items=[item], actor=actor)

    movements_service.write_off_item(db, item=item, actor=actor, comment="Разбит в дороге")

    assert [line.outcome for line in trips_service.lines(db, trip)] == ["written_off"]
    trips_service.close_trip(db, trip=trip)  # nothing left hanging
    assert trip.status is TripStatus.CLOSED


def test_what_travels_with_a_person_is_visible_on_them(db, types, shelf, employee, trip, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    trips_service.take_items(db, trip=trip, items=[item], actor=actor)

    assert [unit.id for unit in trips_service.items_away_with(db, employee)] == [item.id]
    assert [open_trip.id for open_trip in trips_service.open_trips_of(db, employee)] == [trip.id]


def test_overdue_trip_is_one_that_is_late_and_still_holding_things(
    db, types, shelf, employee, trip, actor
):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    trips_service.take_items(db, trip=trip, items=[item], actor=actor)
    trip.returns_on = date.today() - timedelta(days=3)
    db.flush()

    assert [late.id for late in trips_service.overdue_trips(db)] == [trip.id]

    trips_service.return_item(db, trip=trip, item=item, to=LocationRef.storage(shelf.id), actor=actor)
    assert trips_service.overdue_trips(db) == []


def test_a_trip_that_carried_something_cannot_be_deleted(db, types, shelf, trip, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    trips_service.take_items(db, trip=trip, items=[item], actor=actor)
    trips_service.return_item(db, trip=trip, item=item, to=LocationRef.storage(shelf.id), actor=actor)

    with pytest.raises(ServiceError, match="нельзя удалить"):
        trips_service.delete_trip(db, trip=trip)


def test_an_empty_trip_can_be_deleted(db, trip):
    trips_service.delete_trip(db, trip=trip)
    assert trips_service.list_trips(db) == []


def test_the_nesting_rule_holds_on_the_plain_move_too(db, types, shelf, trip, actor):
    """The dedicated button refuses it; the universal «Переместить» must not be a way round."""
    machine = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    stick = make_item(db, types["RAM"], at=LocationRef.inside(machine.id), actor=actor)

    with pytest.raises(ServiceError, match="вложена"):
        movements_service.move_item(
            db,
            item=stick,
            to=LocationRef.trip(trip.id),
            reason=MovementReason.TRIP_OUT,
            actor=actor,
        )
