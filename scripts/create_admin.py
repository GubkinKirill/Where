"""Create or update a login. Run: python -m scripts.create_admin <username>"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.auth.providers import hash_password
from app.db import SessionLocal
from app.models.enums import UserRole
from app.models.user import User


def main() -> int:
    parser = argparse.ArgumentParser(description="Создать учётную запись или сменить пароль")
    parser.add_argument("username")
    parser.add_argument("--role", choices=[role.value for role in UserRole], default="admin")
    parser.add_argument("--full-name", default="")
    args = parser.parse_args()

    password = getpass.getpass("Пароль: ")
    if password != getpass.getpass("Ещё раз: "):
        print("Пароли не совпадают.")
        return 1
    if len(password) < 8:
        print("Пароль короче 8 символов.")
        return 1

    with SessionLocal() as db:
        user = db.scalars(select(User).where(User.username == args.username)).first()
        if user is None:
            user = User(username=args.username)
            db.add(user)
            action = "создана"
        else:
            action = "обновлена"
        user.password_hash = hash_password(password)
        user.role = UserRole(args.role)
        user.is_active = True
        if args.full_name:
            user.full_name = args.full_name
        db.commit()
        print(f"Учётная запись «{args.username}» {action}, роль: {user.role.value}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
