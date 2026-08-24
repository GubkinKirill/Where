"""Accounts and the summary through HTTP, as an administrator uses them."""

import pytest
from fastapi.testclient import TestClient

from app.auth.providers import hash_password
from app.db import get_db
from app.main import app
from app.models.enums import UserRole
from app.models.user import User
from app.services import movements as movements_service
from app.services import users as users_service
from app.services.location import LocationRef
from tests.factories import make_item


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin(db) -> User:
    user = User(
        username="admin",
        full_name="Администратор",
        role=UserRole.ADMIN,
        password_hash=hash_password("admin12345"),
    )
    db.add(user)
    db.flush()
    return user


def sign_in(client, username="admin", password="admin12345"):
    response = client.post(
        "/login", data={"username": username, "password": password}, follow_redirects=False
    )
    assert response.status_code == 303
    return response


def test_staff_lands_on_the_summary(client, admin):
    sign_in(client)
    response = client.get("/", follow_redirects=False)
    assert response.headers["location"] == "/dashboard"


def test_summary_counts_what_is_where(client, db, admin, employee, types, shelf, actor):
    on_shelf = make_item(db, types["MON"], name="Монитор", at=LocationRef.storage(shelf.id))
    issued = make_item(db, types["PC"], name="Системный блок", at=LocationRef.storage(shelf.id))
    movements_service.issue_item(db, item=issued, employee_id=employee.id, actor=actor)
    db.commit()
    sign_in(client)

    page = client.get("/dashboard").text
    assert "Всего на учёте" in page
    assert "У сотрудников" in page
    assert on_shelf.inv_number in page or "На складе" in page


def test_admin_creates_an_employee_account(client, db, admin, employee):
    sign_in(client)
    client.post(
        "/admin/users/new",
        data={
            "username": "petrov",
            "password": "employee12345",
            "role": UserRole.EMPLOYEE.value,
            "employee_id": str(employee.id),
        },
    )
    created = users_service.by_username(db, "petrov")
    assert created is not None
    assert created.employee_id == employee.id
    assert "petrov" in client.get("/admin/users").text


def test_only_admins_see_the_accounts_page(client, db):
    viewer = User(
        username="viewer",
        role=UserRole.VIEWER,
        password_hash=hash_password("viewer12345"),
    )
    db.add(viewer)
    db.commit()
    sign_in(client, "viewer", "viewer12345")
    assert client.get("/admin/users").status_code == 403


def test_password_is_changed_from_the_profile(client, db, admin):
    sign_in(client)
    client.post(
        "/profile/password",
        data={"current_password": "admin12345", "new_password": "brandnew12345"},
    )
    client.post("/logout")
    response = client.post(
        "/login",
        data={"username": "admin", "password": "brandnew12345"},
        follow_redirects=False,
    )
    assert response.status_code == 303
