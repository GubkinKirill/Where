"""Accounts: who may sign in and what the interface refuses to let an admin do."""

import pytest

from app.auth.providers import authenticate, hash_password
from app.models.enums import UserRole
from app.models.user import User
from app.services import users as users_service
from app.services.errors import ServiceError


@pytest.fixture
def admin(db) -> User:
    user = User(
        username="admin",
        role=UserRole.ADMIN,
        password_hash=hash_password("admin12345"),
    )
    db.add(user)
    db.flush()
    return user


def test_created_account_can_sign_in(db, employee):
    users_service.create_user(
        db,
        username="petrov",
        password="employee12345",
        role=UserRole.EMPLOYEE,
        employee_id=employee.id,
    )
    db.flush()
    assert authenticate(db, "petrov", "employee12345") is not None


def test_login_is_unique(db, admin):
    with pytest.raises(ServiceError):
        users_service.create_user(
            db, username="admin", password="another12345", role=UserRole.VIEWER
        )


def test_short_password_is_refused(db):
    with pytest.raises(ServiceError):
        users_service.create_user(db, username="short", password="1234", role=UserRole.VIEWER)


def test_employee_account_needs_an_employee_card(db):
    with pytest.raises(ServiceError):
        users_service.create_user(
            db, username="ghost", password="employee12345", role=UserRole.EMPLOYEE
        )


def test_one_person_one_account(db, employee):
    users_service.create_user(
        db,
        username="petrov",
        password="employee12345",
        role=UserRole.EMPLOYEE,
        employee_id=employee.id,
    )
    db.flush()
    with pytest.raises(ServiceError):
        users_service.create_user(
            db,
            username="petrov2",
            password="employee12345",
            role=UserRole.EMPLOYEE,
            employee_id=employee.id,
        )


def test_last_admin_keeps_the_role(db, admin):
    with pytest.raises(ServiceError):
        users_service.update_user(db, user=admin, role=UserRole.VIEWER)


def test_admin_cannot_demote_themselves(db, admin):
    other = users_service.create_user(
        db, username="second", password="admin12345", role=UserRole.ADMIN
    )
    db.flush()
    assert other.role is UserRole.ADMIN
    with pytest.raises(ServiceError):
        users_service.update_user(db, user=admin, role=UserRole.EDITOR, actor=admin)


def test_password_change_requires_the_old_one(db, admin):
    with pytest.raises(ServiceError):
        users_service.change_own_password(
            db, user=admin, current="wrong-one", new="brandnew12345"
        )
    users_service.change_own_password(
        db, user=admin, current="admin12345", new="brandnew12345"
    )
    db.flush()
    assert authenticate(db, "admin", "brandnew12345") is not None


def test_unlinked_employees_excludes_taken_cards(db, employee):
    assert employee in [e for e in users_service.unlinked_employees(db)]
    users_service.create_user(
        db,
        username="petrov",
        password="employee12345",
        role=UserRole.EMPLOYEE,
        employee_id=employee.id,
    )
    db.flush()
    assert employee not in users_service.unlinked_employees(db)
    # the card stays selectable on the form of the account that holds it
    assert employee in users_service.unlinked_employees(db, keep=employee.id)
