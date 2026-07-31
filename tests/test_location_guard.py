"""The movement log must be impossible to bypass — these tests are the fence."""

import pytest

from app.models.enums import LocationKind
from app.models.item import Item
from app.services.errors import LocationWriteError
from app.services.location import LocationRef
from tests.factories import make_item


def test_direct_placement_edit_is_rejected(db, types, shelf, other_shelf, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    item.loc_storage_place_id = other_shelf.id

    with pytest.raises(LocationWriteError):
        db.flush()


def test_creating_an_item_outside_the_service_is_rejected(db, types, shelf):
    db.add(
        Item(
            inv_number="PC-9999",
            type_id=types["PC"].id,
            name="В обход сервиса",
            loc_kind=LocationKind.STORAGE,
            loc_storage_place_id=shelf.id,
        )
    )

    with pytest.raises(LocationWriteError):
        db.flush()


def test_ordinary_fields_still_save(db, types, shelf, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    item.name = "Переименовано"
    item.serial_number = "SN-1"
    db.flush()

    assert db.get(Item, item.id).name == "Переименовано"
