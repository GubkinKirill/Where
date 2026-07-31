import pytest

from app.models.directory import Employee
from app.models.enums import LocationKind, MovementReason
from app.services import employees as employees_service
from app.services import movements as movements_service
from app.services.errors import ServiceError
from app.services.location import LocationRef
from tests.factories import make_item


@pytest.fixture
def successor(db, room) -> Employee:
    employee = Employee(full_name="Кузнецов Пётр Ильич", default_room_id=room.id)
    db.add(employee)
    db.flush()
    return employee


def test_items_of_lists_only_what_the_person_holds(db, types, shelf, employee, actor):
    held = make_item(db, types["PC"], name="Системный блок", at=LocationRef.storage(shelf.id))
    make_item(db, types["MON"], name="Монитор на полке", at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=held, employee_id=employee.id, actor=actor)

    assert [item.id for item in employees_service.items_of(db, employee)] == [held.id]


def test_transfer_moves_everything_and_logs_each_item(
    db, types, shelf, employee, successor, actor
):
    first = make_item(db, types["PC"], name="Системный блок", at=LocationRef.storage(shelf.id))
    second = make_item(db, types["MON"], name="Монитор", at=LocationRef.storage(shelf.id))
    for item in (first, second):
        movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)

    moved = employees_service.transfer_items(
        db, source=employee, target=successor, actor=actor
    )

    assert len(moved) == 2
    assert employees_service.items_of(db, employee) == []
    assert len(employees_service.items_of(db, successor)) == 2

    for item in (first, second):
        assert item.loc_employee_id == successor.id
        assert item.loc_room_id == successor.default_room_id
        log = movements_service.history(db, item)
        assert log[0].reason is MovementReason.ISSUE
        assert log[0].from_employee_id == employee.id
        assert "Передано от" in log[0].comment


def test_transfer_to_a_dismissed_employee_is_rejected(
    db, types, shelf, employee, successor, actor
):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)
    employees_service.set_active(db, employee=successor, is_active=False)

    with pytest.raises(ServiceError):
        employees_service.transfer_items(db, source=employee, target=successor, actor=actor)

    assert item.loc_employee_id == employee.id


def test_dismissal_leaves_the_equipment_on_the_person(db, types, shelf, employee, actor):
    """Nothing disappears from the books when someone leaves — it has to be moved."""
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)

    employees_service.set_active(db, employee=employee, is_active=False)

    assert item.loc_kind is LocationKind.PERSON
    assert item.loc_employee_id == employee.id
    assert len(employees_service.items_of(db, employee)) == 1


def test_dismissed_employee_cannot_receive_new_items(db, types, shelf, employee, actor):
    employees_service.set_active(db, employee=employee, is_active=False)
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))

    with pytest.raises(ServiceError):
        movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)
