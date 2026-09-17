"""Fill an empty database with a small demo set: python -m scripts.seed_demo

Deliberately small — a handful of items, just enough to see every kind of
placement. Everything goes in through the services, so the movement log is real:
each item has a history you can click through.
"""

import sys
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.auth.providers import hash_password
from app.db import SessionLocal
from app.models.directory import Department, Employee, Room, StoragePlace
from app.models.enums import (
    ItemStatus,
    MovementReason,
    ProjectStatus,
    RequestKind,
    RequestStatus,
    StoragePlaceKind,
    UserRole,
)
from app.models.item import Item, ItemType, NumberSequence
from app.models.kit import KitTemplate, KitTemplateLine
from app.models.project import Project
from app.models.request import EquipmentRequest
from app.models.user import User
from app.schemas.consumable import ConsumableForm
from app.schemas.item import ItemForm
from app.services import consumables as consumables_service
from app.services import items as items_service
from app.services import movements as movements_service
from app.services import trips as trips_service
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
    ("KIT", "Комплект поставки", True, "📦", ["проект", "площадка"], 105),
    ("ANT", "Антенна", False, "📡", [], 106),
    ("BS", "Базовая станция", False, "📶", [], 107),
    ("CBL", "Кабель", False, "〰", [], 108),
    ("NB", "Ноутбук", True, "💻", ["образ ОС", "MAC"], 15),
    ("KVM", "KVM-переключатель", False, "⇄", [], 110),
    ("NET", "Сетевое оборудование", False, "🌐", [], 120),
    ("PRN", "Принтер", False, "🖨", [], 130),
    ("UPS", "ИБП", False, "🔋", [], 140),
    ("OTHER", "Прочее", False, "•", [], 200),
]

# where the demo numbering starts, purely so the numbers look lived-in
NUMBER_HEAD_START = {"PC": 13, "MON": 6, "RAM": 22, "SSD": 10, "RPI": 3, "PSU": 4, "NB": 7}


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
        projects = _seed_projects(db)
        employees = _seed_employees(db, departments, rooms)
        db.flush()
        _seed_employee_accounts(db, employees)

        for prefix, value in NUMBER_HEAD_START.items():
            db.add(NumberSequence(prefix=prefix, last_value=value))
        db.flush()

        _seed_items(db, users, types, places, employees, rooms, projects)
        _seed_trips(db, users, types, places, employees, projects)
        _seed_requests(db, employees)
        _seed_consumables(db, users, places, employees)
        db.commit()

    print(
        "Демо-данные загружены.\n"
        "  Отдел:     admin / admin12345, kgubkin / editor12345, viewer / viewer12345\n"
        "  Сотрудники: petrov / employee12345, novikov / employee12345 (личные кабинеты)\n"
        "  Есть открытая просроченная командировка, командировка в срок и закрытая,\n"
        "  а также три проекта с оборудованием."
    )
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


CONSUMABLES = [
    # name, category, unit, on hand, threshold, place, notes
    ("Мышь проводная USB", "Периферия", "шт.", 6, 3, "shelf2", None),
    ("Клавиатура USB", "Периферия", "шт.", 4, 2, "shelf2", None),
    ("Патч-корд UTP 2 м", "Кабели", "шт.", 12, 10, "shelf2", "Синие, cat.5e"),
    ("Кабель питания C13", "Кабели", "шт.", 2, 5, "shelf2", None),
    ("Переходник HDMI–VGA", "Переходники", "шт.", 0, 2, "shelf2", "Кончились, заказаны"),
    ("Карта microSD 32 ГБ", "Носители", "шт.", 8, 4, "shelf1", "Под образы Raspberry Pi"),
]


def _seed_consumables(db, users, places, employees) -> None:
    """Quantity accounting, with a couple of positions deliberately running low."""
    editor = users["editor"]
    for name, category, unit, quantity, threshold, place, notes in CONSUMABLES:
        stock = consumables_service.create_stock(
            db,
            form=ConsumableForm(
                name=name,
                category=category,
                unit=unit,
                min_quantity=threshold,
                storage_place_id=places[place].id,
                notes=notes,
            ),
            quantity=quantity,
            actor=editor,
            comment="Начальный остаток",
        )
        if name.startswith("Мышь"):
            consumables_service.issue(
                db,
                stock=stock,
                quantity=1,
                employee_id=employees["petrov"].id,
                actor=editor,
                comment="Взамен сломанной",
            )
    db.flush()


def _seed_employee_accounts(db, employees) -> None:
    """Cabinet logins: role «employee», each tied to a card. Novikov is the one
    away on a trip, so his cabinet shows what he took with him."""
    db.add_all(
        [
            User(
                username="petrov",
                full_name="",
                role=UserRole.EMPLOYEE,
                password_hash=hash_password("employee12345"),
                employee_id=employees["petrov"].id,
            ),
            User(
                username="novikov",
                full_name="",
                role=UserRole.EMPLOYEE,
                password_hash=hash_password("employee12345"),
                employee_id=employees["novikov"].id,
            ),
        ]
    )
    db.flush()


def _seed_projects(db) -> dict[str, Project]:
    """Three states worth seeing: running, paused and finished."""
    today = date.today()
    projects = {
        "north": Project(
            code="PRJ-04",
            name="Северный узел",
            customer="ООО «Связь»",
            starts_on=today - timedelta(days=200),
            ends_on=today + timedelta(days=105),
            status=ProjectStatus.ACTIVE,
            notes="Оборудование заказчика, по окончании возвращается ему.",
        ),
        "shop2": Project(
            code="PRJ-07",
            name="Модернизация цеха 2",
            customer="ПАО «Комбинат»",
            starts_on=today - timedelta(days=60),
            ends_on=today + timedelta(days=300),
            status=ProjectStatus.ACTIVE,
        ),
        "pilot": Project(
            code="PRJ-01",
            name="Опытный участок",
            customer="Внутренний",
            starts_on=today - timedelta(days=900),
            ends_on=today - timedelta(days=300),
            status=ProjectStatus.CLOSED,
            notes="Закрыт; часть техники осталась на предприятии.",
        ),
    }
    db.add_all(projects.values())
    db.flush()
    return projects


def _seed_requests(db, employees) -> None:
    db.add_all(
        [
            EquipmentRequest(
                employee_id=employees["petrov"].id,
                kind=RequestKind.NEED,
                text="Нужен второй монитор на рабочее место, работаю с двумя схемами сразу.",
            ),
            EquipmentRequest(
                employee_id=employees["sidorova"].id,
                kind=RequestKind.BROKEN,
                status=RequestStatus.IN_PROGRESS,
                text="Принтер зажёвывает бумагу.",
            ),
        ]
    )
    db.flush()


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
    cabinet = StoragePlace(code="CAB-01", name="Шкаф 1", kind=StoragePlaceKind.CABINET)
    db.add(cabinet)
    db.flush()

    places = {
        "cabinet": cabinet,
        "shelf1": StoragePlace(
            code="SHELF-01", name="Полка 1", kind=StoragePlaceKind.SHELF, parent_id=cabinet.id
        ),
        "shelf2": StoragePlace(
            code="SHELF-02", name="Полка 2", kind=StoragePlaceKind.SHELF, parent_id=cabinet.id
        ),
    }
    db.add_all(places.values())
    return places


def _seed_employees(db, departments, rooms) -> dict[str, Employee]:
    db.flush()
    employees = {
        "petrov": Employee(
            full_name="Петров Иван Сергеевич",
            personnel_number="1042",
            position="Инженер-технолог",
            department_id=departments["235"].id,
            default_room_id=rooms["312"].id,
        ),
        "sidorova": Employee(
            full_name="Сидорова Анна Викторовна",
            personnel_number="0871",
            position="Экономист",
            department_id=departments["117"].id,
            default_room_id=rooms["208"].id,
        ),
        "novikov": Employee(
            full_name="Новиков Сергей Тимофеевич",
            personnel_number="1188",
            position="Инженер связи",
            department_id=departments["235"].id,
            default_room_id=rooms["312"].id,
        ),
        "kozlov": Employee(
            full_name="Козлов Дмитрий Павлович",
            personnel_number="1205",
            position="Монтажник",
            department_id=departments["235"].id,
            default_room_id=rooms["312"].id,
        ),
        "ivanova": Employee(
            full_name="Иванова Мария Олеговна",
            personnel_number="0934",
            position="Бухгалтер",
            department_id=departments["117"].id,
            default_room_id=rooms["208"].id,
        ),
    }
    db.add_all(employees.values())
    return employees


def _seed_items(db, users, types, places, employees, rooms, projects) -> None:
    editor = users["editor"]
    today = date.today()

    def create(type_code, name, *, location, status=ItemStatus.RESERVE, **fields) -> Item:
        form = ItemForm(type_id=types[type_code].id, name=name, status=status, **fields)
        return items_service.create_item(db, form=form, location=location, actor=editor)

    shelf1 = LocationRef.storage(places["shelf1"].id)
    shelf2 = LocationRef.storage(places["shelf2"].id)

    # PC-0014 — a machine with components inside, currently with an employee
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

    installed_at = datetime.now() - timedelta(days=880)
    for type_code, name in [("RAM", "Kingston 8 ГБ DDR4-2666"), ("SSD", "Kingston A400 480 ГБ")]:
        component = create(type_code, name, location=shelf1, manufacturer="Kingston")
        movements_service.move_item(
            db,
            item=component,
            to=LocationRef.inside(pc.id),
            reason=MovementReason.INSTALL,
            actor=editor,
            moved_at=installed_at,
        )
        component.status = ItemStatus.IN_USE

    # history worth clicking through: issued, returned when she left, issued again
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
        comment="Взамен вышедшего из строя системного блока",
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

    # a spare sitting on a shelf
    create(
        "PSU",
        "Блок питания Chieftec 500 Вт",
        location=shelf2,
        manufacturer="Chieftec",
        model="GPE-500S",
    )

    # a single board computer standing in a room, with its own attributes
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

    _seed_kit(db, create, types, shelf1, shelf2, editor, projects["north"])
    _seed_more_equipment(db, create, shelf1, shelf2, employees, rooms, projects, editor)


def _seed_more_equipment(db, create, shelf1, shelf2, employees, rooms, projects, editor) -> None:
    """Enough of everything to have something to move around: desks with machines,
    laptops that travel, a shelf with spares, and equipment that came from projects."""
    # workplaces: a machine and a monitor each
    for key, machine, monitor in [
        ("novikov", "Системный блок Dell OptiPlex 3080", 'Монитор Dell P2419H 24"'),
        ("kozlov", "Системный блок Lenovo M720q", 'Монитор Philips 243V7 24"'),
        ("ivanova", "Системный блок HP ProDesk 400 G7", 'Монитор Acer V226HQL 22"'),
    ]:
        for type_code, name in (("PC", machine), ("MON", monitor)):
            unit = create(type_code, name, location=shelf1)
            movements_service.issue_item(
                db,
                item=unit,
                employee_id=employees[key].id,
                actor=editor,
                comment="Рабочее место",
                moved_at=datetime.now() - timedelta(days=210),
            )

    # laptops: the things that actually go on trips
    create("NB", "Ноутбук Lenovo ThinkPad T14", location=shelf1, manufacturer="Lenovo",
           model="ThinkPad T14 Gen 2", serial_number="PF2XK9L1")
    create("NB", "Ноутбук Dell Latitude 5520", location=shelf1, manufacturer="Dell",
           model="Latitude 5520", serial_number="8HTZ4M3")
    create("NB", "Ноутбук HP ProBook 450", location=shelf2, manufacturer="HP",
           model="ProBook 450 G8")

    # spares on the shelf
    create("MON", 'Монитор LG 22MK400 22"', location=shelf2, manufacturer="LG")
    create("SSD", "Kingston A400 240 ГБ", location=shelf2, manufacturer="Kingston")
    create("RAM", "Crucial 8 ГБ DDR4-3200", location=shelf2, manufacturer="Crucial")
    create("UPS", "ИБП APC Back-UPS 650", location=shelf2, manufacturer="APC",
           status=ItemStatus.REPAIR, condition_note="Не держит батарею, отдан в ремонт")
    create("OTHER", "Тестер кабеля NF-8108", location=shelf2, manufacturer="Noyafa")

    # equipment that came with a project and stays tied to it wherever it goes
    switch = create("NET", "Коммутатор MikroTik CRS310", location=shelf1,
                    manufacturer="MikroTik", project_id=projects["shop2"].id)
    movements_service.move_item(
        db,
        item=switch,
        to=LocationRef.room(rooms["401"].id),
        reason=MovementReason.TO_STORAGE,
        actor=editor,
        comment="Стойка в серверной",
    )
    create("RPI", "Raspberry Pi 4B — шлюз цеха 2", location=shelf2,
           project_id=projects["shop2"].id, manufacturer="Raspberry Pi Foundation")
    create("PRN", "Принтер Kyocera P2040", location=shelf2, manufacturer="Kyocera",
           project_id=projects["pilot"].id,
           notes="Остался на предприятии после закрытия опытного участка")


def _seed_kit(db, create, types, shelf1, shelf2, editor, project) -> None:
    """A half-assembled delivery kit — the case the neighbouring department is stuck on.
    It came with a project, so every part of it is the customer's, not ours."""
    template = KitTemplate(
        name="Комплект базовой станции",
        description="Что должно уехать на площадку одной поставкой",
        lines=[
            KitTemplateLine(item_type_id=types["BS"].id, quantity=1, note="с блоком питания"),
            KitTemplateLine(item_type_id=types["ANT"].id, quantity=2, note="секторные, 65°"),
            KitTemplateLine(item_type_id=types["CBL"].id, quantity=6, note="джампер 1 м, N-типа"),
        ],
    )
    db.add(template)
    db.flush()

    kit = create(
        "KIT",
        "Комплект БС — площадка №3",
        location=shelf2,
        status=ItemStatus.INCOMPLETE,
        project_id=project.id,
    )
    kit.kit_template_id = template.id
    db.flush()

    inside_kit = LocationRef.inside(kit.id)
    packed = [
        create("BS", "Базовая станция Huawei BTS3900", location=shelf1, manufacturer="Huawei",
               project_id=project.id),
        create("ANT", "Антенна секторная Kathrein 742265", location=shelf1,
               manufacturer="Kathrein", project_id=project.id),
    ]
    packed += [
        create("CBL", "Джампер N-N 1 м", location=shelf1, manufacturer="RFS",
               project_id=project.id)
        for _ in range(3)
    ]
    for part in packed:
        movements_service.move_item(
            db,
            item=part,
            to=inside_kit,
            reason=MovementReason.INSTALL,
            actor=editor,
            comment="Уложено в комплект",
        )

    # spares on the shelf: enough for one antenna, not enough for the cables
    create("ANT", "Антенна секторная Kathrein 742265", location=shelf1, manufacturer="Kathrein",
           project_id=project.id)
    for _ in range(2):
        create("CBL", "Джампер N-N 1 м", location=shelf1, manufacturer="RFS",
               project_id=project.id)


def _seed_trips(db, users, types, places, employees, projects) -> None:
    """Three trips, so every state is on screen at once: one overdue with things
    still out there, one that has only just left, and one closed where something
    came back, something stayed on site and something died on the road."""
    editor = users["editor"]
    today = date.today()
    shelf1 = places["shelf1"]

    def on_shelf(name: str) -> Item:
        return db.scalars(select(Item).where(Item.name == name)).first()

    # 1. late: left ten days ago, was due back three days ago, still holding things
    north = trips_service.create_trip(
        db,
        employee=employees["novikov"],
        destination="Новосибирск, площадка «Север»",
        departs_on=today - timedelta(days=10),
        returns_on=today - timedelta(days=3),
        purpose="Монтаж базовой станции",
        project_id=projects["north"].id,
        notes="Связь через мессенджер, возвращение сдвинулось",
    )
    trips_service.take_items(
        db,
        trip=north,
        items=[
            on_shelf("Ноутбук Lenovo ThinkPad T14"),
            on_shelf("Комплект БС — площадка №3"),
            on_shelf("Тестер кабеля NF-8108"),
        ],
        actor=editor,
    )

    # 2. on its way: left today, nothing overdue about it
    omsk = trips_service.create_trip(
        db,
        employee=employees["kozlov"],
        destination="Омск, узел связи",
        departs_on=today,
        returns_on=today + timedelta(days=12),
        purpose="Замена коммутатора",
    )
    trips_service.take_items(
        db,
        trip=omsk,
        items=[on_shelf("Ноутбук Dell Latitude 5520")],
        actor=editor,
        comment="Взял свой рабочий ноутбук",
    )

    # 3. finished: back, left on site, and written off there
    krasnoyarsk = trips_service.create_trip(
        db,
        employee=employees["petrov"],
        destination="Красноярск, цех 2",
        departs_on=today - timedelta(days=60),
        returns_on=today - timedelta(days=45),
        purpose="Пусконаладка шлюза",
        project_id=projects["shop2"].id,
    )
    came_back = on_shelf("Ноутбук HP ProBook 450")
    stayed = on_shelf("Raspberry Pi 4B — шлюз цеха 2")
    broke = on_shelf("Монитор LG 22MK400 22\"")
    trips_service.take_items(db, trip=krasnoyarsk, items=[came_back, stayed, broke], actor=editor)
    trips_service.return_item(
        db,
        trip=krasnoyarsk,
        item=came_back,
        to=LocationRef.storage(shelf1.id),
        actor=editor,
        moved_at=datetime.now() - timedelta(days=45),
    )
    trips_service.leave_item(
        db,
        trip=krasnoyarsk,
        item=stayed,
        note="Цех 2, шкаф автоматики",
        actor=editor,
        comment="Работает на объекте, по акту передан заказчику",
        moved_at=datetime.now() - timedelta(days=46),
    )
    movements_service.write_off_item(
        db, item=broke, actor=editor, comment="Разбит при перевозке, акт от 12 числа"
    )
    trips_service.close_trip(db, trip=krasnoyarsk)
    db.flush()


if __name__ == "__main__":
    sys.exit(main())
