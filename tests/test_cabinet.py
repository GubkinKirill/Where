"""The employee cabinet: own equipment, colleagues, confirmations, requests."""

import pytest
from fastapi.testclient import TestClient

from app.auth.providers import hash_password
from app.db import get_db
from app.main import app
from app.models.directory import Employee
from app.models.enums import RequestStatus, UserRole
from app.models.user import User
from app.services import movements as movements_service
from app.services import requests as requests_service
from app.services.location import LocationRef
from tests.factories import make_item


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def account(db, employee) -> User:
    user = User(
        username="petrov",
        role=UserRole.EMPLOYEE,
        password_hash=hash_password("employee12345"),
        employee_id=employee.id,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def colleague(db) -> Employee:
    other = Employee(full_name="Сидорова Анна Викторовна", position="Экономист")
    db.add(other)
    db.flush()
    return other


def sign_in(client, username="petrov", password="employee12345", next_url="/"):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": next_url},
        follow_redirects=False,
    )


def test_employee_lands_in_the_cabinet(client, account):
    response = sign_in(client, next_url="/items")
    assert response.status_code == 303
    # asked for an accounting page, sent to the one page that concerns them
    assert response.headers["location"] == "/cabinet"


def test_employee_may_not_open_the_accounting_pages(client, account):
    sign_in(client)
    for path in ("/items", "/dashboard", "/movements", "/requests", "/admin/users"):
        assert client.get(path).status_code == 403, path


def test_cabinet_shows_what_is_assigned(client, db, account, employee, types, shelf, actor):
    item = make_item(db, types["MON"], name="Монитор Dell", at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)
    db.commit()
    sign_in(client)

    page = client.get("/cabinet").text
    assert item.inv_number in page
    assert "Монитор Dell" in page
    assert "Ждут вашего подтверждения" in page


def test_confirming_a_handover(client, db, account, employee, types, shelf, actor):
    item = make_item(db, types["MON"], name="Монитор", at=LocationRef.storage(shelf.id))
    movement = movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)
    db.commit()
    sign_in(client)

    client.post("/cabinet/confirm", data={"movement_id": movement.id})
    db.refresh(movement)
    assert movement.acknowledged_at is not None
    assert movement.acknowledged_by_employee_id == employee.id


def test_cannot_confirm_somebody_elses_handover(
    client, db, account, colleague, types, shelf, actor
):
    item = make_item(db, types["MON"], name="Монитор", at=LocationRef.storage(shelf.id))
    movement = movements_service.issue_item(db, item=item, employee_id=colleague.id, actor=actor)
    db.commit()
    sign_in(client)

    client.post("/cabinet/confirm", data={"movement_id": movement.id})
    db.refresh(movement)
    assert movement.acknowledged_at is None


def test_colleagues_list_shows_who_holds_what(
    client, db, account, colleague, types, shelf, actor
):
    item = make_item(db, types["PC"], name="Системный блок", at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=item, employee_id=colleague.id, actor=actor)
    db.commit()
    sign_in(client)

    listing = client.get("/cabinet/colleagues").text
    assert "Сидорова А. В." in listing

    card = client.get(f"/cabinet/colleagues/{colleague.id}").text
    assert item.inv_number in card


def test_search_finds_the_holder_by_inventory_number(
    client, db, account, colleague, types, shelf, actor
):
    item = make_item(db, types["PC"], name="Системный блок", at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=item, employee_id=colleague.id, actor=actor)
    db.commit()
    sign_in(client)

    found = client.get("/cabinet/search", params={"q": item.inv_number}).text
    assert item.inv_number in found
    assert "Сидорова А. В." in found


def test_request_is_filed_and_can_be_withdrawn(client, db, account, employee):
    sign_in(client)

    client.post("/cabinet/requests", data={"kind": "need", "text": "Нужен второй монитор"})
    filed = requests_service.of_employee(db, employee)
    assert len(filed) == 1
    assert filed[0].status is RequestStatus.NEW

    client.post(f"/cabinet/requests/{filed[0].id}/withdraw")
    db.refresh(filed[0])
    assert filed[0].status is RequestStatus.REJECTED


def test_request_cannot_point_at_somebody_elses_item(
    client, db, account, employee, colleague, types, shelf, actor
):
    item = make_item(db, types["PC"], name="Системный блок", at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=item, employee_id=colleague.id, actor=actor)
    db.commit()
    sign_in(client)

    client.post(
        "/cabinet/requests",
        data={"kind": "broken", "text": "Не включается", "item_id": item.id},
    )
    assert requests_service.of_employee(db, employee) == []


def test_account_without_an_employee_card_is_told_so(client, db):
    orphan = User(
        username="nobody",
        role=UserRole.VIEWER,
        password_hash=hash_password("viewer12345"),
    )
    db.add(orphan)
    db.commit()
    sign_in(client, "nobody", "viewer12345")

    response = client.get("/cabinet")
    assert response.status_code == 404
    assert "не привязана к карточке сотрудника" in response.text
