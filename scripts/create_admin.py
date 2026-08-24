"""Create or update a login. Run: python -m scripts.create_admin <username>"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.auth.providers import hash_password
from app.db import SessionLocal
from app.models.directory import Employee
from app.models.enums import UserRole
from app.models.user import User


def main() -> int:
    parser = argparse.ArgumentParser(description="Создать учётную запись или сменить пароль")
    parser.add_argument("username")
    parser.add_argument("--role", choices=[role.value for role in UserRole], default="admin")
    parser.add_argument("--full-name", default="")
    parser.add_argument(
        "--employee",
        default=None,
        metavar="ТАБЕЛЬНЫЙ",
        help="привязать к карточке сотрудника по табельному номеру (нужно для роли employee)",
    )
    args = parser.parse_args()

    role = UserRole(args.role)
    if role is UserRole.EMPLOYEE and not args.employee:
        print("Для роли employee укажите --employee <табельный номер>.")
        return 1

    password = getpass.getpass("Пароль: ")
    if password != getpass.getpass("Ещё раз: "):
        print("Пароли не совпадают.")
        return 1
    if len(password) < 8:
        print("Пароль короче 8 символов.")
        return 1

    with SessionLocal() as db:
        employee = None
        if args.employee:
            employee = db.scalars(
                select(Employee).where(Employee.personnel_number == args.employee)
            ).first()
            if employee is None:
                print(f"Сотрудник с табельным номером {args.employee} не найден.")
                return 1
            taken = db.scalars(select(User).where(User.employee_id == employee.id)).first()
            if taken is not None and taken.username != args.username:
                print(f"У сотрудника уже есть учётная запись «{taken.username}».")
                return 1

        user = db.scalars(select(User).where(User.username == args.username)).first()
        if user is None:
            user = User(username=args.username)
            db.add(user)
            action = "создана"
        else:
            action = "обновлена"
        user.password_hash = hash_password(password)
        user.role = role
        user.is_active = True
        if args.full_name:
            user.full_name = args.full_name
        if employee is not None:
            user.employee_id = employee.id
        db.commit()
        print(f"Учётная запись «{args.username}» {action}, роль: {user.role.value}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
