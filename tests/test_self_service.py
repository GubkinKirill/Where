"""The page an employee opens without any account."""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
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
def numbered(db, employee):
    employee.personnel_number = "1042"
    db.flush()
    return employee


def test_page_opens_without_signing_in(client):
    response = client.get("/my")
    assert response.status_code == 200
    assert "Табельный номер" in response.text


def test_personnel_number_shows_the_equipment(client, db, types, shelf, numbered, actor):
    item = make_item(db, types["PC"], name="Системный блок HP", at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=item, employee_id=numbered.id, actor=actor)
    db.commit()

    response = client.post("/my", data={"personnel_number": "1042"})

    assert response.status_code == 200
    assert item.inv_number in response.text
    assert "Системный блок HP" in response.text


def test_nested_parts_are_listed_with_the_container(
    db, client, types, shelf, numbered, actor
):
    pc = make_item(db, types["PC"], name="Системный блок", at=LocationRef.storage(shelf.id))
    ram = make_item(db, types["RAM"], name="Планка памяти", at=LocationRef.storage(shelf.id))
    movements_service.install_component(db, item=ram, container=pc, actor=actor)
    movements_service.issue_item(db, item=pc, employee_id=numbered.id, actor=actor)
    db.commit()

    response = client.post("/my", data={"personnel_number": "1042"})

    assert ram.inv_number in response.text


def test_unknown_number_says_nothing_useful(client, db, numbered):
    db.commit()

    response = client.post("/my", data={"personnel_number": "9999"})

    assert response.status_code == 404
    assert "не найден" in response.text
    assert numbered.full_name not in response.text


def test_empty_number_is_not_a_match(client, db, numbered):
    db.commit()

    response = client.post("/my", data={"personnel_number": "  "})

    assert response.status_code == 404
