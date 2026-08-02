import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.directory import Employee
from app.services import movements as movements_service
from app.services.errors import MoveError
from app.services.location import LocationRef
from tests.factories import make_item


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def numbered(db, employee) -> Employee:
    employee.personnel_number = "1042"
    db.flush()
    return employee


@pytest.fixture
def issued(db, types, shelf, numbered, actor):
    item = make_item(db, types["PC"], name="Системный блок", at=LocationRef.storage(shelf.id))
    movement = movements_service.issue_item(
        db, item=item, employee_id=numbered.id, actor=actor
    )
    return movement


def test_issue_starts_out_unconfirmed(db, issued, numbered):
    assert issued.acknowledged_at is None
    assert issued.needs_acknowledgement
    assert movements_service.pending_acknowledgements(db, numbered) == [issued]
    assert movements_service.unacknowledged(db) == [issued]


def test_recipient_confirms_once(db, issued, numbered):
    movements_service.acknowledge(db, movement=issued, employee=numbered)

    assert issued.acknowledged_at is not None
    assert issued.acknowledged_by_employee_id == numbered.id
    assert movements_service.pending_acknowledgements(db, numbered) == []
    assert movements_service.unacknowledged(db) == []

    with pytest.raises(MoveError):
        movements_service.acknowledge(db, movement=issued, employee=numbered)


def test_somebody_else_cannot_confirm(db, issued, room):
    stranger = Employee(full_name="Чужой Человек", personnel_number="9999")
    db.add(stranger)
    db.flush()

    with pytest.raises(MoveError):
        movements_service.acknowledge(db, movement=issued, employee=stranger)

    assert issued.acknowledged_at is None


def test_returned_item_needs_no_confirmation(db, issued, numbered, shelf, actor):
    movements_service.return_to_storage(
        db, item=issued.item, storage_place_id=shelf.id, actor=actor
    )

    assert not issued.needs_acknowledgement
    assert movements_service.pending_acknowledgements(db, numbered) == []


def test_confirmation_through_the_self_service_page(client, db, issued, numbered):
    db.commit()

    listing = client.post("/my", data={"personnel_number": "1042"})
    assert "Ждут вашего подтверждения" in listing.text

    confirmed = client.post(
        "/my/confirm",
        data={"personnel_number": "1042", "movement_id": str(issued.id)},
    )
    assert confirmed.status_code == 200
    assert "подтверждено" in confirmed.text

    db.refresh(issued)
    assert issued.acknowledged_at is not None


def test_confirmation_with_a_wrong_number_changes_nothing(client, db, issued, numbered):
    db.commit()

    response = client.post(
        "/my/confirm",
        data={"personnel_number": "0000", "movement_id": str(issued.id)},
    )

    assert response.status_code == 404
    db.refresh(issued)
    assert issued.acknowledged_at is None
