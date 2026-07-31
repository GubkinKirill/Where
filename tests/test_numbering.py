from app.models.enums import MovementReason
from app.services import movements as movements_service
from app.services.location import LocationRef
from app.services.numbering import next_inv_number
from tests.factories import make_item


def test_numbers_increment_within_prefix(db, types):
    assert next_inv_number(db, "PC") == "PC-0001"
    assert next_inv_number(db, "PC") == "PC-0002"
    assert next_inv_number(db, "RAM") == "RAM-0001"
    assert next_inv_number(db, "PC") == "PC-0003"


def test_number_is_not_reused_after_write_off(db, types, shelf, actor):
    at_shelf = LocationRef.storage(shelf.id)
    first = make_item(db, types["PC"], at=at_shelf, actor=actor)
    assert first.inv_number == "PC-0001"

    movements_service.write_off_item(db, item=first, actor=actor)

    second = make_item(db, types["PC"], at=at_shelf, actor=actor)
    assert second.inv_number == "PC-0002"


def test_created_item_gets_a_register_movement(db, types, shelf, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    log = movements_service.history(db, item)
    assert len(log) == 1
    assert log[0].reason is MovementReason.REGISTER
    assert log[0].from_kind is None
    assert log[0].to_storage_place_id == shelf.id
    assert log[0].to_label == "склад · Полка 1"
