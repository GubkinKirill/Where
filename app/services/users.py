"""Accounts: who may sign in, with which role, on behalf of which person.

Kept apart from the employee directory on purpose: a person exists in the books
whether or not they ever log in, and an account may outlive the link to a person.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.providers import hash_password, verify_password
from app.models.directory import Employee
from app.models.enums import UserRole
from app.models.user import User
from app.services.errors import ServiceError

MIN_PASSWORD_LENGTH = 8


def all_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.role, User.username)))


def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def by_username(db: Session, username: str) -> Optional[User]:
    return db.scalars(select(User).where(func.lower(User.username) == username.lower())).first()


def create_user(
    db: Session,
    *,
    username: str,
    password: str,
    role: UserRole,
    full_name: str = "",
    employee_id: Optional[int] = None,
) -> User:
    username = (username or "").strip()
    if not username:
        raise ServiceError("Укажите логин.")
    if by_username(db, username) is not None:
        raise ServiceError(f"Логин «{username}» уже занят.")
    _check_password(password)
    _check_link(role, employee_id)

    user = User(
        username=username,
        full_name=(full_name or "").strip(),
        role=role,
        password_hash=hash_password(password),
    )
    _link_employee(db, user, employee_id)
    db.add(user)
    db.flush()
    return user


def update_user(
    db: Session,
    *,
    user: User,
    role: UserRole,
    full_name: str = "",
    employee_id: Optional[int] = None,
    is_active: bool = True,
    actor: Optional[User] = None,
) -> User:
    if actor is not None and actor.id == user.id:
        # locking yourself out of the only admin account is the one mistake
        # nobody can undo from the interface
        if role is not UserRole.ADMIN:
            raise ServiceError("Нельзя понизить себе роль.")
        if not is_active:
            raise ServiceError("Нельзя отключить собственную учётную запись.")
    if user.role is UserRole.ADMIN and role is not UserRole.ADMIN and _admin_count(db) <= 1:
        raise ServiceError("Это последний администратор. Сначала назначьте другого.")

    _check_link(role, employee_id)
    user.role = role
    user.full_name = (full_name or "").strip()
    user.is_active = is_active
    _link_employee(db, user, employee_id)
    db.flush()
    return user


def set_password(db: Session, *, user: User, password: str) -> User:
    _check_password(password)
    user.password_hash = hash_password(password)
    db.flush()
    return user


def change_own_password(db: Session, *, user: User, current: str, new: str) -> User:
    """Requires the old password: a session left open must not become a hijacked login."""
    if not verify_password(user, current):
        raise ServiceError("Текущий пароль указан неверно.")
    if current == new:
        raise ServiceError("Новый пароль совпадает со старым.")
    return set_password(db, user=user, password=new)


def account_of(db: Session, employee: Employee) -> Optional[User]:
    return db.scalars(select(User).where(User.employee_id == employee.id)).first()


def unlinked_employees(db: Session, *, keep: Optional[int] = None) -> list[Employee]:
    """People who have no account yet — plus the one already linked to the account
    being edited, so it stays selectable."""
    taken = set(db.scalars(select(User.employee_id).where(User.employee_id.is_not(None))))
    taken.discard(keep)
    return [
        employee
        for employee in db.scalars(
            select(Employee).where(Employee.is_active).order_by(Employee.full_name)
        )
        if employee.id not in taken
    ]


# --- internals ---------------------------------------------------------------


def _check_link(role: UserRole, employee_id: Optional[int]) -> None:
    if role is UserRole.EMPLOYEE and employee_id is None:
        raise ServiceError(
            "Учётной записи сотрудника нужна карточка сотрудника: кабинет показывает "
            "то, что закреплено за человеком."
        )


def _check_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ServiceError(f"Пароль короче {MIN_PASSWORD_LENGTH} символов.")


def _admin_count(db: Session) -> int:
    return db.scalar(
        select(func.count(User.id)).where(User.role == UserRole.ADMIN, User.is_active)
    ) or 0


def _link_employee(db: Session, user: User, employee_id: Optional[int]) -> None:
    if employee_id is None:
        user.employee_id = None
        return
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise ServiceError("Сотрудник не найден.")
    holder = account_of(db, employee)
    if holder is not None and holder.id != user.id:
        raise ServiceError(
            f"У сотрудника {employee.short_name} уже есть учётная запись «{holder.username}»."
        )
    user.employee_id = employee.id
