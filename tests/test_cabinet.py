"""The employee cabinet: own equipment, colleagues, confirmations, requests."""

import pytest
from fastapi.testclient import TestClient

from app.auth.providers import hash_password
from app.db import get_db
from app.main import app
from app.models.directory import Employee
from app.models.enums import LocationKind, MovementReason, UserRole
from app.models.user import User
from app.services import employees as employees_service
from app.services import movements as movements_service
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
    for path in ("/items", "/dashboard", "/movements", "/trips", "/admin/users"):
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


def test_employee_hands_an_item_to_a_colleague(client, db, account, employee, colleague, types, shelf, actor):
    item = make_item(db, types["PC"], name="Монитор Dell", at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)
    db.commit()
    sign_in(client)

    page = client.get("/cabinet").text
    assert f"/cabinet/hand-over/{item.id}" in page

    client.post(f"/cabinet/hand-over/{item.id}", data={"recipient_id": colleague.id})
    db.refresh(item)

    assert item.loc_employee_id == colleague.id
    log = movements_service.history(db, item)[0]
    assert log.reason is MovementReason.ISSUE
    assert log.from_employee_id == employee.id
    assert log.recipient_employee_id == colleague.id
    assert log.moved_by_user_id == account.id  # автор записи — сам сотрудник
    assert "Передано между сотрудниками" in log.comment
    # получатель ещё не подтвердил, отдел это видит
    assert log.needs_acknowledgement
    assert movements_service.unacknowledged(db) == [log]
    # у передавшего выдача закрыта, вещь за ним больше не числится
    assert employees_service.items_of(db, employee) == []


def test_employee_cannot_hand_over_what_is_not_theirs(
    client, db, account, employee, colleague, types, shelf, actor
):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=item, employee_id=colleague.id, actor=actor)
    db.commit()
    sign_in(client)

    form = client.get(f"/cabinet/hand-over/{item.id}")
    posted = client.post(f"/cabinet/hand-over/{item.id}", data={"recipient_id": employee.id})
    db.refresh(item)

    assert form.status_code == 404
    assert posted.status_code == 400
    assert item.loc_employee_id == colleague.id


def test_handover_to_a_dismissed_colleague_is_refused(
    client, db, account, employee, colleague, types, shelf, actor
):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)
    colleague.is_active = False
    db.commit()
    sign_in(client)

    response = client.post(f"/cabinet/hand-over/{item.id}", data={"recipient_id": colleague.id})
    db.refresh(item)

    assert response.status_code == 400
    assert "уволен" in response.text
    assert item.loc_employee_id == employee.id


def test_the_cabinet_still_moves_nothing_else(client, db, account, employee, types, shelf, actor):
    """Передача своего — единственное перемещение, доступное сотруднику."""
    spare = make_item(db, types["MON"], at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client)

    assert client.get(f"/items/{spare.id}/issue").status_code == 403
    assert client.get(f"/items/{spare.id}/move").status_code == 403
    assert client.get(f"/items/{spare.id}/write-off").status_code == 403
    assert client.post(f"/items/{spare.id}/return", data={}).status_code == 403
    db.refresh(spare)
    assert spare.loc_kind is LocationKind.STORAGE
