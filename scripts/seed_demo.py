"""Fill an empty database with demo data: python -m scripts.seed_demo

Everything goes in through the services, so the movement log is real: every item
has a history you can click through.
"""

import sys
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.auth.providers import hash_password
from app.db import SessionLocal
from app.models.directory import Department, Employee, Room, StoragePlace
from app.models.enums import ItemStatus, MovementReason, StoragePlaceKind, UserRole
from app.models.item import Item, ItemType, NumberSequence
from app.models.user import User
from app.schemas.item import ItemForm
from app.services import items as items_service
from app.services import movements as movements_service
from app.services.location import LocationRef

ITEM_TYPES = [
    ("PC", "Системный блок", True, "🖥", [], 10),
    ("MON", "Монитор", False, "🖵", [], 20),
    ("RAM", "Модуль памяти", False, "▤", [], 30),
    ("SSD", "Накопитель SSD", False, "▪", [], 40),
    ("HDD", "Жёсткий диск", False, "▪", [], 50),
    ("PSU", "Блок питания", False, "⚡", [], 60),
    ("GPU", "Видеокарта", False, "▦", [], 70),
    ("MB", "Материнская плата", False, "▩", [], 80),
    ("CPU", "Процессор", False, "◫", [], 90),
    (
        "RPI",
        "Raspberry Pi",
        True,
        "🍓",
        ["назначение", "образ ОС", "MAC", "IP", "версия платы"],
        100,
    ),
    ("KVM", "KVM-переключатель", False, "⇄", [], 110),
    ("NET", "Сетевое оборудование", False, "🌐", [], 120),
    ("PRN", "Принтер", False, "🖨", [], 130),
    ("UPS", "ИБП", False, "🔋", [], 140),
    ("OTHER", "Прочее", False, "•", [], 200),
]

# where the demo numbering starts, purely so the demo matches the mockups
NUMBER_HEAD_START = {"PC": 8, "MON": 6, "RAM": 22, "SSD": 10, "HDD": 30, "RPI": 3, "PSU": 4}


def main() -> int:
    with SessionLocal() as db:
        if db.scalar(select(func.count(Item.id))):
            print("В базе уже есть единицы учёта. Удалите файл БД, если нужен чистый демо-набор.")
            return 1

        users = _seed_users(db)
        types = _seed_types(db)
        rooms = _seed_rooms(db)
        departments = _seed_departments(db)
        places = _seed_storage(db)
        employees = _seed_employees(db, departments, rooms)
        db.flush()

        for prefix, value in NUMBER_HEAD_START.items():
            db.add(NumberSequence(prefix=prefix, last_value=value))
        db.flush()

        _seed_items(db, users, types, places, employees, rooms)
        db.commit()

    print("Демо-данные загружены. Вход: admin / admin12345")
    return 0


def _seed_users(db) -> dict[str, User]:
    users = {
        "admin": User(
            username="admin",
            full_name="Администратор",
            role=UserRole.ADMIN,
            password_hash=hash_password("admin12345"),
        ),
        "editor": User(
            username="kgubkin",
            full_name="Губкин К.",
            role=UserRole.EDITOR,
            password_hash=hash_password("editor12345"),
        ),
        "viewer": User(
            username="viewer",
            full_name="Наблюдатель",
            role=UserRole.VIEWER,
            password_hash=hash_password("viewer12345"),
        ),
    }
    db.add_all(users.values())
    return users


def _seed_types(db) -> dict[str, ItemType]:
    types = {
        code: ItemType(
            code=code,
            name=name,
            is_container=is_container,
            icon=icon,
            suggested_attributes=attributes,
            sort_order=order,
        )
        for code, name, is_container, icon, attributes, order in ITEM_TYPES
    }
    db.add_all(types.values())
    return types


def _seed_rooms(db) -> dict[str, Room]:
    rooms = {
        "312": Room(number="312", floor=3, description="Технический отдел"),
        "208": Room(number="208", floor=2, description="Бухгалтерия"),
        "401": Room(number="401", floor=4, description="Серверная"),
        "114": Room(number="114", floor=1, description="Мастерская"),
    }
    db.add_all(rooms.values())
    return rooms


def _seed_departments(db) -> dict[str, Department]:
    departments = {
        "235": Department(code="235", name="Технический отдел"),
        "117": Department(code="117", name="Бухгалтерия"),
    }
    db.add_all(departments.values())
    return departments


def _seed_storage(db) -> dict[str, StoragePlace]:
    cabinet1 = StoragePlace(code="CAB-01", name="Шкаф 1", kind=StoragePlaceKind.CABINET)
    cabinet2 = StoragePlace(code="CAB-02", name="Шкаф 2", kind=StoragePlaceKind.CABINET)
    db.add_all([cabinet1, cabinet2])
    db.flush()

    places = {
        "cab1": cabinet1,
        "cab2": cabinet2,
        "shelf1": StoragePlace(
            code="SHELF-01", name="Полка 1", kind=StoragePlaceKind.SHELF, parent_id=cabinet1.id
        ),
        "shelf2": StoragePlace(
            code="SHELF-02", name="Полка 2", kind=StoragePlaceKind.SHELF, parent_id=cabinet1.id
        ),
        "shelf3": StoragePlace(
            code="SHELF-03", name="Полка 3", kind=StoragePlaceKind.SHELF, parent_id=cabinet1.id
        ),
        "shelf4": StoragePlace(
            code="SHELF-04", name="Полка 1", kind=StoragePlaceKind.SHELF, parent_id=cabinet2.id
        ),
    }
    db.add_all(places.values())
    db.flush()

    places["cellA"] = StoragePlace(
        code="CELL-A", name="Ячейка A", kind=StoragePlaceKind.CELL, parent_id=places["shelf4"].id
    )
    db.add(places["cellA"])
    return places


def _seed_employees(db, departments, rooms) -> dict[str, Employee]:
    db.flush()
    employees = {
        "petrov": Employee(
            full_name="Петров Иван Сергеевич",
            position="Инженер-технолог",
            department_id=departments["235"].id,
            default_room_id=rooms["312"].id,
        ),
        "sidorova": Employee(
            full_name="Сидорова Анна Викторовна",
            position="Экономист",
            department_id=departments["117"].id,
            default_room_id=rooms["208"].id,
        ),
        "petrova": Employee(
            full_name="Петрова Мария Львовна",
            position="Бухгалтер",
            department_id=departments["117"].id,
            default_room_id=rooms["208"].id,
        ),
        "petrenko": Employee(
            full_name="Петренко Олег Юрьевич",
            position="Слесарь КИПиА",
            department_id=departments["235"].id,
            default_room_id=rooms["114"].id,
        ),
    }
    db.add_all(employees.values())
    return employees


def _seed_items(db, users, types, places, employees, rooms) -> None:
    editor = users["editor"]
    today = date.today()

    def create(type_code, name, *, location, status=ItemStatus.RESERVE, **fields) -> Item:
        form = ItemForm(type_id=types[type_code].id, name=name, status=status, **fields)
        return items_service.create_item(db, form=form, location=location, actor=editor)

    shelf1 = LocationRef.storage(places["shelf1"].id)
    shelf2 = LocationRef.storage(places["shelf2"].id)
    shelf3 = LocationRef.storage(places["shelf3"].id)
    cell_a = LocationRef.storage(places["cellA"].id)

    # PC-0009 — donor, taken apart on a shelf
    create(
        "PC",
        "Системный блок Dell OptiPlex 3050",
        location=shelf3,
        status=ItemStatus.DONOR,
        manufacturer="Dell",
        model="OptiPlex 3050 SFF",
        serial_number="8HJ2K33",
        legacy_number="235-42",
        condition_note="Не стартует, подозрение на материнскую плату",
        purchase_date=today - timedelta(days=2500),
    )

    # cosmetic: makes the demo machine below come out as PC-0014, as in the mockups
    db.get(NumberSequence, "PC").last_value = 13
    db.flush()

    # PC-0014 — the machine from the mockups
    pc = create(
        "PC",
        "Системный блок HP ProDesk 400 G6",
        location=shelf1,
        manufacturer="HP",
        model="ProDesk 400 G6 SFF",
        serial_number="CZC0123XYZ",
        legacy_number="235-70",
        condition_note="Не работает один передний USB-порт",
        purchase_date=today - timedelta(days=1600),
        warranty_until=today - timedelta(days=500),
    )
    inside_pc = LocationRef.inside(pc.id)

    components = [
        create("RAM", "Kingston 8 ГБ DDR4-2666", location=shelf1, manufacturer="Kingston"),
        create("RAM", "Kingston 8 ГБ DDR4-2666", location=shelf1, manufacturer="Kingston"),
        create("SSD", "Kingston A400 480 ГБ", location=shelf1, manufacturer="Kingston", model="A400"),
    ]

    installed_at = datetime.now() - timedelta(days=880)
    for component in components:
        movements_service.move_item(
            db,
            item=component,
            to=inside_pc,
            reason=MovementReason.INSTALL,
            actor=editor,
            moved_at=installed_at,
        )
        component.status = ItemStatus.IN_USE

    # a failing disk that is still inside the machine
    hdd = create("HDD", "WD Blue 1 ТБ", location=shelf1, manufacturer="Western Digital")
    movements_service.move_item(
        db,
        item=hdd,
        to=inside_pc,
        reason=MovementReason.INSTALL,
        actor=editor,
        moved_at=datetime.now() - timedelta(days=330),
        comment="Добавлен для архива",
    )
    hdd.status = ItemStatus.REPAIR
    hdd.condition_note = "Щёлкает при старте, данные перенесены"

    # PC-0014 went to Sidorova, came back when she left, then went to Petrov
    movements_service.issue_item(
        db,
        item=pc,
        employee_id=employees["sidorova"].id,
        room_id=rooms["208"].id,
        actor=editor,
        moved_at=datetime.now() - timedelta(days=1520),
    )
    movements_service.return_to_storage(
        db,
        item=pc,
        storage_place_id=places["shelf2"].id,
        actor=editor,
        comment="Сотрудник уволен",
        moved_at=datetime.now() - timedelta(days=970),
    )
    employees["sidorova"].is_active = False
    movements_service.issue_item(
        db,
        item=pc,
        employee_id=employees["petrov"].id,
        actor=editor,
        comment="Взамен вышедшего из строя PC-0009",
        moved_at=datetime.now() - timedelta(days=880),
    )

    monitor = create(
        "MON",
        'Монитор Dell P2419H 24"',
        location=shelf2,
        manufacturer="Dell",
        model="P2419H",
        legacy_number="235-71",
        purchase_date=today - timedelta(days=1600),
    )
    movements_service.issue_item(
        db, item=monitor, employee_id=employees["petrov"].id, actor=editor
    )

    create(
        "PSU",
        "Блок питания Chieftec 500 Вт",
        location=cell_a,
        manufacturer="Chieftec",
        model="GPE-500S",
    )

    # Raspberry Pi kit standing in the server room
    pi = create(
        "RPI",
        "Raspberry Pi 4B 4 ГБ — стенд опроса счётчиков",
        location=shelf2,
        status=ItemStatus.IN_USE,
        manufacturer="Raspberry Pi Foundation",
        model="4 Model B 4GB",
    )
    items_service.update_item(
        db,
        item=pi,
        form=ItemForm(
            type_id=types["RPI"].id,
            name=pi.name,
            status=ItemStatus.IN_USE,
            manufacturer=pi.manufacturer,
            model=pi.model,
        ),
        attributes={
            "назначение": "Опрос счётчиков электроэнергии, цех 2",
            "образ ОС": "Raspberry Pi OS Lite 64-bit, 2025-05",
            "MAC": "dc:a6:32:11:22:33",
            "IP": "192.168.10.41",
            "версия платы": "4B rev 1.4",
        },
    )
    movements_service.move_item(
        db,
        item=pi,
        to=LocationRef.room(rooms["401"].id),
        reason=MovementReason.TO_STORAGE,
        actor=editor,
        comment="Установлен на стойку",
    )

    sd_card = create("OTHER", "SD-карта SanDisk 32 ГБ", location=shelf2)
    movements_service.move_item(
        db,
        item=sd_card,
        to=LocationRef.inside(pi.id),
        reason=MovementReason.INSTALL,
        actor=editor,
    )
    sd_card.status = ItemStatus.IN_USE

    # something handed over to another department
    old_printer = create(
        "PRN", "Принтер HP LaserJet 1020", location=shelf3, manufacturer="HP", model="LaserJet 1020"
    )
    movements_service.move_item(
        db,
        item=old_printer,
        to=LocationRef.external("Отдел 117, Петровой М. Л."),
        reason=MovementReason.TRANSFER_OUT,
        actor=editor,
        comment="Передан по служебной записке",
    )


if __name__ == "__main__":
    sys.exit(main())
