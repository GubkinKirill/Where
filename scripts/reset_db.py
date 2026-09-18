"""Опустошить базу.

    python -m scripts.reset_db --admin ivanov --full-name "Иванов И. И."
    python -m scripts.reset_db --keep-people --keep-types

Первый способ — для боевого старта с нуля: справочники, сотрудники, единицы,
журнал, расходники, проекты и командировки стираются, остаётся один вход,
с которого всё заводится заново.

Второй — чтобы убрать тестовое наполнение, когда люди уже заведены по-настоящему:
`--keep-people` сохраняет карточки сотрудников и все учётные записи, а стирает
только то, что вокруг них — единицы, журнал, склад, расходники, проекты,
командировки и справочники мест. Ссылки сотрудников на отдел и кабинет при этом
очищаются: сами справочники стёрты, и указывать им некуда.

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

from sqlalchemy import delete, func, select, text, update

from app.auth.providers import hash_password
from app.db import SessionLocal
from app.models.consumable import ConsumableMovement, ConsumableStock
from app.models.directory import Department, Employee, Room, StoragePlace
from app.models.enums import UserRole
from app.models.item import Item, ItemAttribute, ItemType, NumberSequence
from app.models.kit import KitTemplate, KitTemplateLine
from app.models.movement import Movement
from app.models.project import Project
from app.models.trip import Trip
from app.models.user import User

# кого сохраняет --keep-people: сами люди и их входы в систему
PEOPLE = (User, Employee)

# порядок важен: сначала то, что ссылается, потом то, на что ссылаются
WIPE_ORDER = [
    ConsumableMovement,
    ConsumableStock,
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
    parser = argparse.ArgumentParser(description="Очистить базу")
    parser.add_argument("--admin", metavar="ЛОГИН", help="учётка администратора, которая останется")
    parser.add_argument("--full-name", default="")
    parser.add_argument(
        "--keep-people",
        action="store_true",
        help="сохранить сотрудников и учётные записи, стереть только данные вокруг них",
    )
    types = parser.add_mutually_exclusive_group()
    types.add_argument("--keep-types", action="store_true", help="сохранить типы единиц как есть")
    types.add_argument("--with-types", action="store_true", help="загрузить стандартный набор типов")
    parser.add_argument("--yes", action="store_true", help="не спрашивать подтверждения")
    args = parser.parse_args()

    if not args.keep_people and not args.admin:
        parser.error("укажите --admin: иначе после очистки в базу некому будет войти")

    wipe = [model for model in WIPE_ORDER if not (args.keep_people and model in PEOPLE)]

    with SessionLocal() as db:
        totals = {model.__tablename__: len(list(db.scalars(select(model)))) for model in wipe}
        kept_people = (
            db.scalar(select(func.count(Employee.id))),
            db.scalar(select(func.count(User.id))),
        )
        linked = db.scalar(
            select(func.count(Employee.id)).where(
                (Employee.department_id.is_not(None)) | (Employee.default_room_id.is_not(None))
            )
        )

    filled = {name: n for name, n in totals.items() if n}
    print("Будет стёрто:")
    for name, n in filled.items():
        print(f"  {name}: {n}")
    if not filled:
        print("  — стирать нечего")
    if args.keep_people:
        print(f"\nСохраняются: сотрудников {kept_people[0]}, учётных записей {kept_people[1]}.")
        if linked:
            print(
                f"У {linked} из них очистятся ссылки на отдел и кабинет: "
                "эти справочники стираются, и указывать станет некуда."
            )

    if not args.yes:
        if input('Стереть безвозвратно? Введите «да»: ').strip().lower() != "да":
            print("Отменено.")
            return 1

    admin_values = None
    if args.admin is not None:
        admin_values = _admin_account(args)
        if admin_values is None:
            return 1

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
        if args.keep_people:
            # сотрудники остаются, а отделы и кабинеты — нет: обнуляем ссылки,
            # иначе карточки повиснут на несуществующих записях
            db.execute(update(Employee).values(department_id=None, default_room_id=None))
        for model in wipe:
            db.execute(delete(model))
        db.execute(delete(ItemType))

        source = kept_types if args.keep_types else (STANDARD_TYPES if args.with_types else [])
        for code, name, is_container, order in source:
            db.add(ItemType(code=code, name=name, is_container=is_container, sort_order=order))

        if admin_values is not None:
            username, full_name, password_hash = admin_values
            db.add(
                User(
                    username=username,
                    full_name=full_name,
                    role=UserRole.ADMIN,
                    password_hash=password_hash,
                    is_active=True,
                )
            )
        db.commit()

    if args.keep_people:
        print(f"\nБаза очищена. Сотрудники и учётные записи на месте: "
              f"{kept_people[0]} и {kept_people[1]}.")
    else:
        print(f"\nБаза очищена. Вход: {args.admin}, роль admin.")
    print(f"Типов единиц: {len(source)}" if source else "Типов единиц нет — заведите их в справочниках.")
    return 0


def _admin_account(args):
    """Логин, имя и хеш пароля для администратора, который останется после очистки.

    Существующую учётку сохраняем вместе с паролем — тогда скрипт ничего не
    спрашивает и никаких паролей не печатает. Новую заводим, спросив пароль."""
    with SessionLocal() as db:
        existing = db.scalars(select(User).where(User.username == args.admin)).first()
        kept = (
            (existing.username, existing.full_name, existing.password_hash)
            if existing is not None
            else None
        )

    if kept is not None:
        print(f"\nУчётка «{args.admin}» уже есть — сохраняю её вместе с паролем.")
        return args.admin, args.full_name or kept[1], kept[2]

    password = getpass.getpass("Пароль администратора: ")
    if password != getpass.getpass("Ещё раз: "):
        print("Пароли не совпадают.")
        return None
    if len(password) < 8:
        print("Пароль короче 8 символов.")
        return None
    return args.admin, args.full_name or args.admin, hash_password(password)


if __name__ == "__main__":
    sys.exit(main())
