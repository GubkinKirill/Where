"""Наполнить существующую базу тестовой техникой, чтобы было на чём потренироваться.

    python -m scripts.seed_sandbox

В отличие от scripts.seed_demo, который разворачивает демо-набор с нуля вместе со
своими сотрудниками и учётками, этот скрипт работает поверх уже заведённой базы:
берёт тех сотрудников, что в ней есть, и добавляет к ним справочники, технику,
склад, проекты, командировки и расходники.

Учётные записи и карточки сотрудников не создаются, не меняются и не удаляются —
скрипт проверяет это сам и прерывается, если счётчики разошлись.

Всё заведённое — обычные записи, и убирается обычным путём:

    python -m scripts.reset_db --admin <логин> --keep-types

Скрипт отказывается работать, если единицы уже заведены: дописывать тестовое
к боевому учёту нельзя.
"""

import sys
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.directory import Department, Employee, Room, StoragePlace
from app.models.enums import (
    ItemStatus,
    MovementReason,
    ProjectStatus,
    StoragePlaceKind,
    UserRole,
)
from app.models.item import Item, ItemType
from app.models.kit import KitTemplate, KitTemplateLine
from app.models.project import Project
from app.models.user import User
from app.schemas.consumable import ConsumableForm
from app.schemas.item import ItemForm
from app.services import consumables as consumables_service
from app.services import items as items_service
from app.services import movements as movements_service
from app.services import trips as trips_service
from app.services.location import LocationRef


def main() -> int:
    with SessionLocal() as db:
        if db.scalar(select(func.count(Item.id))):
            print(
                "В базе уже есть единицы учёта — тестовое к ним не дописывается.\n"
                "Очистите базу (python -m scripts.reset_db --admin ЛОГИН --keep-types)\n"
                "или загрузите демо-набор в отдельный файл: DB_PATH=data/demo.db."
            )
            return 1

        people = list(db.scalars(select(Employee).where(Employee.is_active).order_by(Employee.id)))
        if not people:
            print("В базе нет работающих сотрудников — некому выдавать технику.")
            return 1

        types = {t.code: t for t in db.scalars(select(ItemType))}
        missing = [code for code in ("PC", "NB", "MON", "RAM", "SSD", "KIT") if code not in types]
        if missing:
            print(f"Не хватает типов единиц: {', '.join(missing)}. Заведите их в справочнике.")
            return 1

        before = (
            db.scalar(select(func.count(User.id))),
            db.scalar(select(func.count(Employee.id))),
        )
        actor = _actor(db)

        rooms = _rooms(db)
        _departments(db)
        places = _storage(db)
        projects = _projects(db)
        db.flush()

        _workplaces(db, types, places, people, actor)
        _spares(db, types, places, projects, rooms, actor)
        _kit(db, types, places, projects, actor)
        _trips(db, types, places, people, projects, actor)
        _consumables(db, places, people, actor)

        after = (
            db.scalar(select(func.count(User.id))),
            db.scalar(select(func.count(Employee.id))),
        )
        if after != before:
            db.rollback()
            print(f"Отменено: изменилось число учёток или сотрудников {before} → {after}.")
            return 1

        db.commit()
        _report(db)
    return 0


def _actor(db):
    """От чьего имени пишутся записи журнала: редактор, иначе администратор."""
    return db.scalars(
        select(User)
        .where(User.role.in_((UserRole.EDITOR, UserRole.ADMIN)), User.is_active)
        .order_by(User.role)
    ).first()


def _rooms(db) -> dict[str, Room]:
    rooms = {
        "312": Room(number="312", floor=3, description="Лаборатория"),
        "314": Room(number="314", floor=3, description="Конструкторы"),
        "401": Room(number="401", floor=4, description="Серверная"),
    }
    db.add_all(rooms.values())
    return rooms


def _departments(db) -> dict[str, Department]:
    departments = {
        "ЛАБ": Department(code="ЛАБ", name="Лаборатория"),
        "КБ": Department(code="КБ", name="Конструкторское бюро"),
    }
    db.add_all(departments.values())
    return departments


def _storage(db) -> dict[str, StoragePlace]:
    cabinet = StoragePlace(code="CAB-01", name="Шкаф 1", kind=StoragePlaceKind.CABINET)
    spare_cabinet = StoragePlace(code="CAB-02", name="Шкаф 2", kind=StoragePlaceKind.CABINET)
    db.add_all([cabinet, spare_cabinet])
    db.flush()

    places = {
        "cab1": cabinet,
        "cab2": spare_cabinet,
        "shelf1": StoragePlace(code="SHELF-01", name="Полка 1", parent_id=cabinet.id),
        "shelf2": StoragePlace(code="SHELF-02", name="Полка 2", parent_id=cabinet.id),
        "shelf3": StoragePlace(code="SHELF-03", name="Полка 1", parent_id=spare_cabinet.id),
        "cell1": StoragePlace(
            code="CELL-01", name="Ячейка А", kind=StoragePlaceKind.CELL, parent_id=spare_cabinet.id
        ),
    }
    db.add_all(places.values())
    return places


def _projects(db) -> dict[str, Project]:
    today = date.today()
    projects = {
        "telemetry": Project(
            code="PRJ-01",
            name="Стенд телеметрии",
            customer="Внутренний заказ",
            starts_on=today - timedelta(days=150),
            ends_on=today + timedelta(days=120),
            status=ProjectStatus.ACTIVE,
            notes="Тестовые данные",
        ),
        "upgrade": Project(
            code="PRJ-02",
            name="Модернизация участка",
            customer="ПАО «Комбинат»",
            starts_on=today - timedelta(days=70),
            ends_on=today + timedelta(days=250),
            status=ProjectStatus.ACTIVE,
        ),
        "prototype": Project(
            code="PRJ-03",
            name="Опытный образец",
            customer="Внутренний заказ",
            starts_on=today - timedelta(days=800),
            ends_on=today - timedelta(days=260),
            status=ProjectStatus.CLOSED,
        ),
    }
    db.add_all(projects.values())
    return projects


# что стоит на рабочем месте: чередуем системники и ноутбуки, чтобы было и то и другое
WORKPLACES = [
    ("PC", "Системный блок Dell OptiPlex 7080", "MON", 'Монитор Dell P2419H 24"'),
    ("NB", "Ноутбук Lenovo ThinkPad T14", "MON", 'Монитор Philips 243V7 24"'),
    ("PC", "Системный блок HP ProDesk 400 G7", "MON", 'Монитор LG 24MK430 24"'),
    ("PC", "Системный блок Lenovo M720q", "MON", 'Монитор AOC 24B2XH 24"'),
    ("NB", "Ноутбук HP ProBook 450 G8", None, None),
    ("PC", "Системный блок Dell OptiPlex 3080", "MON", 'Монитор Acer V226HQL 22"'),
    ("PC", "Системный блок ASUS D500MA", "MON", 'Монитор Samsung S24R350 24"'),
    ("NB", "Ноутбук ASUS ExpertBook B1", None, None),
    ("PC", "Системный блок Acer Veriton X2665G", "MON", 'Монитор BenQ GW2480 24"'),
    ("PC", "Системный блок Dell Vostro 3888", "MON", 'Монитор Dell E2420H 24"'),
]


def _workplaces(db, types, places, people, actor) -> None:
    """Каждому работающему сотруднику — рабочее место, выданное полгода назад."""
    shelf = LocationRef.storage(places["shelf1"].id)
    issued_at = datetime.now() - timedelta(days=190)

    for index, person in enumerate(people):
        machine_code, machine_name, monitor_code, monitor_name = WORKPLACES[
            index % len(WORKPLACES)
        ]
        machine = _create(db, types, machine_code, machine_name, shelf, actor)
        movements_service.issue_item(
            db,
            item=machine,
            employee_id=person.id,
            actor=actor,
            comment="Рабочее место",
            moved_at=issued_at + timedelta(days=index),
        )
        if monitor_code:
            monitor = _create(db, types, monitor_code, monitor_name, shelf, actor)
            movements_service.issue_item(
                db,
                item=monitor,
                employee_id=person.id,
                actor=actor,
                comment="Рабочее место",
                moved_at=issued_at + timedelta(days=index),
            )

        # в первые два системника вложены память и накопитель
        if index < 2 and machine_code == "PC":
            for code, name in (("RAM", "Kingston 8 ГБ DDR4-2666"), ("SSD", "Kingston A400 480 ГБ")):
                part = _create(db, types, code, name, shelf, actor)
                movements_service.move_item(
                    db,
                    item=part,
                    to=LocationRef.inside(machine.id),
                    reason=MovementReason.INSTALL,
                    actor=actor,
                    comment="Установлено при сборке",
                    moved_at=issued_at,
                )
                part.status = ItemStatus.IN_USE
    db.flush()


def _spares(db, types, places, projects, rooms, actor) -> None:
    """Запас на полках, техника в кабинетах и оборудование проектов."""
    shelf2 = LocationRef.storage(places["shelf2"].id)
    shelf3 = LocationRef.storage(places["shelf3"].id)
    cell = LocationRef.storage(places["cell1"].id)

    for code, name, where in [
        ("MON", 'Монитор LG 22MK400 22"', shelf2),
        ("MON", 'Монитор Acer K202HQL 20"', shelf2),
        ("RAM", "Crucial 8 ГБ DDR4-3200", cell),
        ("RAM", "Samsung 4 ГБ DDR3-1600", cell),
        ("SSD", "Crucial BX500 240 ГБ", cell),
        ("HDD", "WD Blue 1 ТБ", shelf3),
        ("PSU", "Блок питания Chieftec 500 Вт", shelf3),
        ("KBD", "Клавиатура Logitech K120", shelf2),
        ("NB", "Ноутбук Dell Latitude 5520", shelf2),
    ]:
        _create(db, types, code, name, where, actor)

    donor = _create(db, types, "PC", "Системный блок HP Compaq 6300 (под разбор)", shelf3, actor)
    donor.status = ItemStatus.DONOR

    ups = _create(db, types, "UPS", "ИБП APC Back-UPS 650", shelf3, actor)
    ups.status = ItemStatus.REPAIR
    ups.condition_note = "Не держит батарею, отдан в ремонт"

    # в серверной, но не за человеком
    switch = _create(
        db, types, "NET", "Коммутатор MikroTik CRS310", shelf2, actor,
        project_id=projects["upgrade"].id,
    )
    movements_service.move_item(
        db,
        item=switch,
        to=LocationRef.room(rooms["401"].id),
        reason=MovementReason.TO_STORAGE,
        actor=actor,
        comment="Стойка в серверной",
    )
    printer = _create(db, types, "MFU", "МФУ Kyocera M2040dn", shelf2, actor)
    movements_service.move_item(
        db,
        item=printer,
        to=LocationRef.room(rooms["312"].id),
        reason=MovementReason.TO_STORAGE,
        actor=actor,
        comment="Общий принтер лаборатории",
    )

    # оборудование проектов: принадлежность не меняется при перемещениях
    for code, name, project_key, where in [
        ("SBC", "Raspberry Pi 4B — узел телеметрии", "telemetry", shelf2),
        ("SBC", "Raspberry Pi 4B — резервный узел", "telemetry", shelf2),
        ("NET", "Роутер Keenetic Giga", "telemetry", shelf2),
        ("OTH", "Тестер кабеля NF-8108", "upgrade", shelf2),
        ("PRN", "Принтер этикеток Zebra ZD220", "prototype", shelf3),
        ("MON", 'Монитор Iiyama XU2493 24"', "prototype", shelf3),
    ]:
        _create(db, types, code, name, where, actor, project_id=projects[project_key].id)
    db.flush()


def _kit(db, types, places, projects, actor) -> None:
    """Комплект поставки по шаблону — собран наполовину, как это обычно и бывает."""
    template = KitTemplate(
        name="Комплект выездного стенда",
        description="Что должно уехать на площадку одной поставкой",
        lines=[
            KitTemplateLine(item_type_id=types["SBC"].id, quantity=1, note="с блоком питания"),
            KitTemplateLine(item_type_id=types["NET"].id, quantity=1, note="роутер"),
            KitTemplateLine(item_type_id=types["OTH"].id, quantity=3, note="кабели и переходники"),
        ],
    )
    db.add(template)
    db.flush()

    shelf = LocationRef.storage(places["shelf2"].id)
    kit = _create(
        db, types, "KIT", "Комплект стенда — площадка №1", shelf, actor,
        project_id=projects["upgrade"].id,
    )
    kit.kit_template_id = template.id
    kit.status = ItemStatus.INCOMPLETE
    db.flush()

    packed = [
        _create(db, types, "SBC", "Raspberry Pi 4B — в составе стенда", shelf, actor,
                project_id=projects["upgrade"].id),
        _create(db, types, "NET", "Роутер Keenetic Lite — в составе стенда", shelf, actor,
                project_id=projects["upgrade"].id),
        _create(db, types, "OTH", "Кабель питания C13", shelf, actor,
                project_id=projects["upgrade"].id),
    ]
    for part in packed:
        movements_service.move_item(
            db,
            item=part,
            to=LocationRef.inside(kit.id),
            reason=MovementReason.INSTALL,
            actor=actor,
            comment="Уложено в комплект",
        )

    # на складе есть один подходящий кабель, второго не хватает — это видно на «Комплектах»
    _create(db, types, "OTH", "Кабель питания C13", shelf, actor,
            project_id=projects["upgrade"].id)
    db.flush()


def _trips(db, types, places, people, projects, actor) -> None:
    """Три поездки: просроченная, только что выехавшая и закрытая."""
    today = date.today()
    shelf = places["shelf2"]

    def free(name: str) -> Item:
        return db.scalars(
            select(Item).where(Item.name == name).order_by(Item.id.desc())
        ).first()

    traveller = people[min(8, len(people) - 1)]
    fitter = people[min(7, len(people) - 1)]
    designer = people[min(5, len(people) - 1)]

    late = trips_service.create_trip(
        db,
        employee=traveller,
        destination="Тюмень, площадка заказчика",
        departs_on=today - timedelta(days=8),
        returns_on=today - timedelta(days=2),
        purpose="Пусконаладка стенда телеметрии",
        project_id=projects["telemetry"].id,
        notes="Возвращение сдвинулось, техника ещё на объекте",
    )
    trips_service.take_items(
        db,
        trip=late,
        items=[
            free("Ноутбук Dell Latitude 5520"),
            free("Комплект стенда — площадка №1"),
            free("Тестер кабеля NF-8108"),
        ],
        actor=actor,
    )

    ongoing = trips_service.create_trip(
        db,
        employee=fitter,
        destination="Омск, узел связи",
        departs_on=today,
        returns_on=today + timedelta(days=10),
        purpose="Замена коммутатора",
        project_id=projects["upgrade"].id,
    )
    trips_service.take_items(
        db,
        trip=ongoing,
        items=[free("Роутер Keenetic Giga")],
        actor=actor,
        comment="Взял подменный роутер",
    )

    finished = trips_service.create_trip(
        db,
        employee=designer,
        destination="Красноярск, цех 2",
        departs_on=today - timedelta(days=55),
        returns_on=today - timedelta(days=40),
        purpose="Монтаж опытного образца",
        project_id=projects["prototype"].id,
    )
    came_back = free('Монитор Acer K202HQL 20"')
    stayed = free("Принтер этикеток Zebra ZD220")
    broken = free('Монитор Iiyama XU2493 24"')
    trips_service.take_items(db, trip=finished, items=[came_back, stayed, broken], actor=actor)
    trips_service.return_item(
        db,
        trip=finished,
        item=came_back,
        to=LocationRef.storage(shelf.id),
        actor=actor,
        moved_at=datetime.now() - timedelta(days=40),
    )
    trips_service.leave_item(
        db,
        trip=finished,
        item=stayed,
        note="Цех 2, шкаф автоматики",
        actor=actor,
        comment="Передан заказчику по акту",
        moved_at=datetime.now() - timedelta(days=41),
    )
    movements_service.write_off_item(
        db, item=broken, actor=actor, comment="Разбит при перевозке, составлен акт"
    )
    trips_service.close_trip(db, trip=finished)
    db.flush()


CONSUMABLES = [
    ("Мышь проводная USB", "Периферия", 8, 3, "shelf2", None),
    ("Клавиатура USB", "Периферия", 5, 2, "shelf2", None),
    ("Патч-корд UTP 2 м", "Кабели", 14, 10, "shelf2", "Синие, cat.5e"),
    ("Кабель питания C13", "Кабели", 3, 5, "shelf2", "Заканчиваются"),
    ("Переходник HDMI–VGA", "Переходники", 0, 2, "cell1", "Кончились, заказаны"),
    ("Карта microSD 32 ГБ", "Носители", 10, 4, "cell1", "Под образы одноплатников"),
    ("Батарейка CR2032", "Прочее", 12, 6, "cell1", None),
]


def _consumables(db, places, people, actor) -> None:
    for name, category, quantity, threshold, place, notes in CONSUMABLES:
        stock = consumables_service.create_stock(
            db,
            form=ConsumableForm(
                name=name,
                category=category,
                unit="шт.",
                min_quantity=threshold,
                storage_place_id=places[place].id,
                notes=notes,
            ),
            quantity=quantity,
            actor=actor,
            comment="Начальный остаток",
        )
        if name.startswith("Мышь"):
            consumables_service.issue(
                db,
                stock=stock,
                quantity=1,
                employee_id=people[0].id,
                actor=actor,
                comment="Взамен сломанной",
            )
    db.flush()


def _create(db, types, code, name, location, actor, **fields) -> Item:
    return items_service.create_item(
        db,
        form=ItemForm(type_id=types[code].id, name=name, **fields),
        location=location,
        actor=actor,
    )


def _report(db) -> None:
    from app.models.movement import Movement
    from app.models.trip import Trip

    counts = {
        "единиц учёта": db.scalar(select(func.count(Item.id))),
        "записей в журнале": db.scalar(select(func.count(Movement.id))),
        "проектов": db.scalar(select(func.count(Project.id))),
        "командировок": db.scalar(select(func.count(Trip.id))),
        "мест хранения": db.scalar(select(func.count(StoragePlace.id))),
    }
    print("Тестовые данные добавлены:")
    for name, value in counts.items():
        print(f"  {name}: {value}")
    print(
        "\nУчётные записи и карточки сотрудников не тронуты.\n"
        "Убрать тестовое: python -m scripts.reset_db --admin ЛОГИН --keep-types"
    )


if __name__ == "__main__":
    sys.exit(main())
