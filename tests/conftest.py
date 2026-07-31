import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services  # noqa: F401  registers the placement guard
from app.models import Base
from app.models.directory import Employee, Room, StoragePlace
from app.models.enums import StoragePlaceKind, UserRole
from app.models.item import ItemType
from app.models.user import User


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def types(db) -> dict[str, ItemType]:
    values = {
        "PC": ItemType(code="PC", name="Системный блок", is_container=True),
        "RAM": ItemType(code="RAM", name="Модуль памяти"),
        "MON": ItemType(code="MON", name="Монитор"),
    }
    db.add_all(values.values())
    db.flush()
    return values


@pytest.fixture
def shelf(db) -> StoragePlace:
    place = StoragePlace(code="SHELF-01", name="Полка 1", kind=StoragePlaceKind.SHELF)
    db.add(place)
    db.flush()
    return place


@pytest.fixture
def other_shelf(db) -> StoragePlace:
    place = StoragePlace(code="SHELF-02", name="Полка 2", kind=StoragePlaceKind.SHELF)
    db.add(place)
    db.flush()
    return place


@pytest.fixture
def room(db) -> Room:
    value = Room(number="312", floor=3)
    db.add(value)
    db.flush()
    return value


@pytest.fixture
def employee(db, room) -> Employee:
    value = Employee(full_name="Петров Иван Сергеевич", default_room_id=room.id)
    db.add(value)
    db.flush()
    return value


@pytest.fixture
def actor(db) -> User:
    user = User(username="tester", full_name="Тестер", role=UserRole.EDITOR)
    db.add(user)
    db.flush()
    return user
