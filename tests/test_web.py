"""End to end through HTTP: sign in, look at a card, hand an item over."""

import pytest
from fastapi.testclient import TestClient

from app.auth.providers import hash_password
from app.db import get_db
from app.main import app
from app.models.enums import ItemStatus, LocationKind, UserRole
from app.models.user import User
from app.services.location import LocationRef
from tests.factories import make_item


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def editor(db) -> User:
    user = User(
        username="editor",
        full_name="Редактор",
        role=UserRole.EDITOR,
        password_hash=hash_password("secret12345"),
    )
    db.add(user)
    db.flush()
    return user


def sign_in(client, username="editor", password="secret12345"):
    response = client.post(
        "/login", data={"username": username, "password": password}, follow_redirects=False
    )
    assert response.status_code == 303
    return response


def test_anonymous_is_redirected_to_login(client):
    response = client.get("/items", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/items"


def test_wrong_password_is_refused(client, editor):
    response = client.post("/login", data={"username": "editor", "password": "nope"})
    assert response.status_code == 401


def test_list_and_card(client, db, editor, types, shelf):
    item = make_item(db, types["PC"], name="Системный блок HP", at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "editor")

    listing = client.get("/items")
    assert listing.status_code == 200
    assert item.inv_number in listing.text

    card = client.get(f"/items/{item.id}")
    assert card.status_code == 200
    assert "Системный блок HP" in card.text
    assert "Полка 1" in card.text


def test_search_filters_the_list(client, db, editor, types, shelf):
    make_item(db, types["PC"], name="Системный блок HP", at=LocationRef.storage(shelf.id))
    make_item(db, types["MON"], name="Монитор Dell", at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "editor")

    found = client.get("/items", params={"q": "Монитор"})
    assert "Монитор Dell" in found.text
    assert "Системный блок HP" not in found.text


def test_issue_through_the_web_form(client, db, editor, types, shelf, employee):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "editor")

    response = client.post(
        f"/items/{item.id}/issue",
        data={"loc_kind": "person", "employee_id": str(employee.id)},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db.refresh(item)
    assert item.loc_kind is LocationKind.PERSON
    assert item.loc_employee_id == employee.id
    assert item.status is ItemStatus.IN_USE


def test_viewer_cannot_open_the_issue_form(client, db, types, shelf):
    viewer = User(
        username="viewer",
        role=UserRole.VIEWER,
        password_hash=hash_password("secret12345"),
    )
    db.add(viewer)
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "viewer")

    response = client.get(f"/items/{item.id}/issue")
    assert response.status_code == 403
