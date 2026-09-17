"""Trips and projects through HTTP: the screens a person actually clicks."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth.providers import hash_password
from app.db import get_db
from app.main import app
from app.models.enums import LocationKind, TripStatus, UserRole
from app.models.project import Project
from app.models.user import User
from app.services import trips as trips_service
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


@pytest.fixture
def viewer(db) -> User:
    user = User(
        username="viewer",
        full_name="Наблюдатель",
        role=UserRole.VIEWER,
        password_hash=hash_password("secret12345"),
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def project(db) -> Project:
    record = Project(code="PRJ-04", name="Северный узел", customer="ООО «Связь»")
    db.add(record)
    db.flush()
    return record


def sign_in(client, username="editor"):
    response = client.post(
        "/login",
        data={"username": username, "password": "secret12345"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_a_trip_is_created_and_shown(client, db, editor, employee, project):
    db.commit()
    sign_in(client)

    response = client.post(
        "/trips/new",
        data={
            "employee_id": str(employee.id),
            "destination": "Новосибирск, площадка «Север»",
            "purpose": "Монтаж",
            "project_id": str(project.id),
            "departs_on": date.today().isoformat(),
            "returns_on": (date.today() + timedelta(days=10)).isoformat(),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/take")

    listing = client.get("/trips")
    assert "TRIP-0001" in listing.text
    assert "Новосибирск" in listing.text


def test_a_trip_without_a_destination_comes_back_as_a_form(client, db, editor, employee):
    db.commit()
    sign_in(client)

    response = client.post(
        "/trips/new",
        data={
            "employee_id": str(employee.id),
            "destination": "  ",
            "departs_on": date.today().isoformat(),
        },
    )

    assert response.status_code == 400
    assert "Укажите, куда едет сотрудник" in response.text
    assert trips_service.list_trips(db) == []


def test_packing_and_unpacking_a_trip(client, db, editor, employee, types, shelf):
    trip = trips_service.create_trip(
        db, employee=employee, destination="Омск", departs_on=date.today()
    )
    item = make_item(db, types["PC"], name="Ноутбук Dell", at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client)

    taken = client.post(
        f"/trips/{trip.id}/take", data={"item_id": str(item.id)}, follow_redirects=False
    )
    assert taken.status_code == 303
    assert item.loc_kind is LocationKind.TRIP

    card = client.get(f"/trips/{trip.id}")
    assert "Ноутбук Dell" in card.text
    assert "в командировке" in card.text

    returned = client.post(
        f"/trips/{trip.id}/return/{item.id}",
        data={"loc_kind": "storage", "storage_place_id": str(shelf.id)},
        follow_redirects=False,
    )
    assert returned.status_code == 303
    assert item.loc_kind is LocationKind.STORAGE


def test_closing_is_refused_while_something_is_out(client, db, editor, employee, types, shelf):
    trip = trips_service.create_trip(
        db, employee=employee, destination="Омск", departs_on=date.today()
    )
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))
    trips_service.take_items(db, trip=trip, items=[item])
    db.commit()
    sign_in(client)

    response = client.post(f"/trips/{trip.id}/close", follow_redirects=True)

    assert "Не решена судьба" in response.text
    assert trip.status is TripStatus.OPEN

    client.post(f"/trips/{trip.id}/leave/{item.id}", data={"note": "Площадка"})
    client.post(f"/trips/{trip.id}/close")
    db.refresh(trip)
    assert trip.status is TripStatus.CLOSED


def test_the_item_card_offers_the_trip_and_follows_it(client, db, editor, employee, types, shelf):
    trip = trips_service.create_trip(
        db, employee=employee, destination="Омск", departs_on=date.today()
    )
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client)

    card = client.get(f"/items/{item.id}")
    assert f"/items/{item.id}/to-trip" in card.text

    client.post(f"/items/{item.id}/to-trip", data={"trip_id": str(trip.id)})

    card = client.get(f"/items/{item.id}")
    assert "Омск" in card.text
    assert f"/trips/{trip.id}/return/{item.id}" in card.text


def test_a_viewer_may_look_but_not_pack(client, db, viewer, employee, types, shelf):
    trip = trips_service.create_trip(
        db, employee=employee, destination="Омск", departs_on=date.today()
    )
    db.commit()
    sign_in(client, "viewer")

    assert client.get("/trips").status_code == 200
    assert client.get(f"/trips/{trip.id}").status_code == 200
    assert client.get(f"/trips/{trip.id}/take").status_code == 403
    assert client.get("/trips/new").status_code == 403


def test_project_card_shows_its_equipment_and_where_it_is(
    client, db, editor, employee, types, shelf, project
):
    from app.schemas.item import ItemForm
    from app.services import items as items_service

    item = items_service.create_item(
        db,
        form=ItemForm(type_id=types["MON"].id, name="Монитор проекта", project_id=project.id),
        location=LocationRef.storage(shelf.id),
    )
    db.commit()
    sign_in(client)

    listing = client.get("/projects")
    assert "PRJ-04" in listing.text

    card = client.get(f"/projects/{project.id}")
    assert "Монитор проекта" in card.text
    assert "Полка 1" in card.text
    assert item.inv_number in card.text

    filtered = client.get(f"/items?owner={project.id}")
    assert item.inv_number in filtered.text


def test_employee_card_and_cabinet_show_what_travelled(db, client, employee, types, shelf, editor):
    trip = trips_service.create_trip(
        db, employee=employee, destination="Норильск", departs_on=date.today()
    )
    item = make_item(db, types["PC"], name="Тестер кабеля", at=LocationRef.storage(shelf.id))
    trips_service.take_items(db, trip=trip, items=[item])
    account = User(
        username="petrov",
        role=UserRole.EMPLOYEE,
        password_hash=hash_password("secret12345"),
        employee_id=employee.id,
    )
    db.add(account)
    db.commit()

    sign_in(client)
    card = client.get(f"/employees/{employee.id}")
    assert "Увезено в командировку" in card.text
    assert "Тестер кабеля" in card.text
    client.post("/logout")

    sign_in(client, "petrov")
    cabinet = client.get("/cabinet")
    assert "Норильск" in cabinet.text
    assert "Тестер кабеля" in cabinet.text


def test_dashboard_counts_what_is_away(client, db, editor, employee, types, shelf):
    trip = trips_service.create_trip(
        db, employee=employee, destination="Омск", departs_on=date.today()
    )
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))
    trips_service.take_items(db, trip=trip, items=[item])
    db.commit()
    sign_in(client)

    dashboard = client.get("/dashboard")

    assert "В командировках" in dashboard.text
    assert "Открытые командировки" in dashboard.text
    assert "Омск" in dashboard.text
