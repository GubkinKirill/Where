"""Опустошить базу и оставить одну учётную запись администратора.

    python -m scripts.reset_db --admin ivanov --full-name "Иванов И. И."

Для боевого старта после знакомства с демо-набором: справочники, сотрудники,
единицы, журнал, расходники, заявки, проекты и командировки стираются, остаётся
один вход, с которого всё заводится заново.

Если учётка с таким логином уже есть, она сохраняется вместе с паролем —
скрипт ничего не спрашивает и никаких паролей не показывает. Для новой
учётки пароль спрашивается так же, как в scripts.create_admin.

Типы единиц можно оставить: --keep-types сохранит существующие, --with-types
загрузит стандартный набор (системный блок, монитор, память, накопители…).
Без единого типа нельзя завести ни одну единицу, а набор одинаков везде.
"""

import argparse
import getpass
import sys

from sqlalchemy import delete, select, text

from app.auth.providers import hash_password
from app.db import SessionLocal
from app.models.consumable import ConsumableMovement, ConsumableStock
from app.models.directory import Department, Employee, Room, StoragePlace
from app.models.enums import UserRole
from app.models.item import Item, ItemAttribute, ItemType, NumberSequence
from app.models.kit import KitTemplate, KitTemplateLine
from app.models.movement import Movement
from app.models.project import Project
from app.models.request import EquipmentRequest
from app.models.trip import Trip
from app.models.user import User

# порядок важен: сначала то, что ссылается, потом то, на что ссылаются
WIPE_ORDER = [
    ConsumableMovement,
    ConsumableStock,
    EquipmentRequest,
    Movement,
    ItemAttribute,
    Item,
    KitTemplateLine,
    KitTemplate,
    NumberSequence,
    Trip,
    Project,
    User,
    Employee,
    Room,
    StoragePlace,
    Department,
]

STANDARD_TYPES = [
    ("PC", "Системный блок", True, 10),
    ("NB", "Ноутбук", True, 20),
    ("MON", "Монитор", False, 30),
    ("RAM", "Модуль памяти", False, 40),
    ("SSD", "Накопитель SSD", False, 50),
    ("HDD", "Жёсткий диск", False, 60),
    ("PSU", "Блок питания", False, 70),
    ("GPU", "Видеокарта", False, 80),
    ("MB", "Материнская плата", False, 90),
    ("CPU", "Процессор", False, 100),
    ("KBD", "Клавиатура", False, 110),
    ("MOU", "Мышь", False, 120),
    ("PRN", "Принтер", False, 130),
    ("MFU", "МФУ", False, 140),
    ("UPS", "ИБП", False, 150),
    ("NET", "Сетевое оборудование", False, 160),
    ("SBC", "Одноплатный компьютер", True, 170),
    ("KIT", "Комплект поставки", True, 180),
    ("OTH", "Прочее", False, 190),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Очистить базу, оставив одного администратора")
    parser.add_argument("--admin", required=True, metavar="ЛОГИН")
    parser.add_argument("--full-name", default="")
    types = parser.add_mutually_exclusive_group()
    types.add_argument("--keep-types", action="store_true", help="сохранить типы единиц как есть")
    types.add_argument("--with-types", action="store_true", help="загрузить стандартный набор типов")
    parser.add_argument("--yes", action="store_true", help="не спрашивать подтверждения")
    args = parser.parse_args()

    with SessionLocal() as db:
        totals = {
            model.__tablename__: len(list(db.scalars(select(model)))) for model in WIPE_ORDER
        }
    filled = {name: n for name, n in totals.items() if n}
    print("Будет стёрто:")
    for name, n in filled.items():
        print(f"  {name}: {n}")
    if not filled:
        print("  — база и так пуста")

    if not args.yes:
        if input('Стереть безвозвратно? Введите «да»: ').strip().lower() != "да":
            print("Отменено.")
            return 1

    with SessionLocal() as db:
        existing = db.scalars(select(User).where(User.username == args.admin)).first()
        kept_admin = (
            (existing.username, existing.full_name, existing.password_hash)
            if existing is not None
            else None
        )

    if kept_admin is not None:
        print(f"\nУчётка «{args.admin}» уже есть — сохраняю её вместе с паролем.")
        password_hash = kept_admin[2]
        full_name = args.full_name or kept_admin[1]
    else:
        password = getpass.getpass("Пароль администратора: ")
        if password != getpass.getpass("Ещё раз: "):
            print("Пароли не совпадают.")
            return 1
        if len(password) < 8:
            print("Пароль короче 8 символов.")
            return 1
        password_hash = hash_password(password)
        full_name = args.full_name or args.admin

    kept_types = []
    with SessionLocal() as db:
        if args.keep_types:
            kept_types = [
                (t.code, t.name, t.is_container, t.sort_order)
                for t in db.scalars(select(ItemType).order_by(ItemType.sort_order))
            ]
        # проверку связей откладываем до конца: таблицы ссылаются друг на друга
        # и на самих себя (единица внутри единицы, полка внутри шкафа)
        db.execute(text("PRAGMA defer_foreign_keys=ON"))
        for model in WIPE_ORDER:
            db.execute(delete(model))
        db.execute(delete(ItemType))

        source = kept_types if args.keep_types else (STANDARD_TYPES if args.with_types else [])
        for code, name, is_container, order in source:
            db.add(ItemType(code=code, name=name, is_container=is_container, sort_order=order))

        db.add(
            User(
                username=args.admin,
                full_name=full_name,
                role=UserRole.ADMIN,
                password_hash=password_hash,
                is_active=True,
            )
        )
        db.commit()

    print(f"\nБаза очищена. Вход: {args.admin}, роль admin.")
    print(f"Типов единиц: {len(source)}" if source else "Типов единиц нет — заведите их в справочниках.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
