import pytest

from app.models.enums import ItemStatus, LocationKind
from app.models.item import ItemType
from app.models.kit import KitTemplate, KitTemplateLine
from app.services import kits as kits_service
from app.services import movements as movements_service
from app.services import tree
from app.services.errors import MoveError
from app.services.location import LocationRef
from tests.factories import make_item


@pytest.fixture
def kit_types(db) -> dict[str, ItemType]:
    values = {
        "KIT": ItemType(code="KIT", name="Комплект поставки", is_container=True),
        "ANT": ItemType(code="ANT", name="Антенна"),
        "BS": ItemType(code="BS", name="Базовая станция"),
        "CBL": ItemType(code="CBL", name="Кабель"),
    }
    db.add_all(values.values())
    db.flush()
    return values


@pytest.fixture
def template(db, kit_types) -> KitTemplate:
    value = KitTemplate(
        name="Комплект базовой станции",
        lines=[
            KitTemplateLine(item_type_id=kit_types["BS"].id, quantity=1),
            KitTemplateLine(item_type_id=kit_types["ANT"].id, quantity=2),
            KitTemplateLine(item_type_id=kit_types["CBL"].id, quantity=6),
        ],
    )
    db.add(value)
    db.flush()
    return value


@pytest.fixture
def kit(db, kit_types, template, shelf, actor):
    value = make_item(db, kit_types["KIT"], name="Комплект на площадку", at=LocationRef.storage(shelf.id))
    value.kit_template_id = template.id
    db.flush()
    return value


def pack(db, kit, item_type, shelf, actor, count=1):
    packed = []
    for _ in range(count):
        part = make_item(db, item_type, name=item_type.name, at=LocationRef.storage(shelf.id))
        movements_service.install_component(db, item=part, container=kit, actor=actor)
        packed.append(part)
    return packed


def test_empty_kit_is_missing_everything(db, kit, template):
    status = kits_service.status(db, kit)

    assert status.required_total == 9
    assert status.present_total == 0
    assert status.missing_total == 9
    assert not status.is_complete


def test_partially_packed_kit_counts_what_is_inside(db, kit, kit_types, shelf, actor):
    pack(db, kit, kit_types["BS"], shelf, actor)
    pack(db, kit, kit_types["ANT"], shelf, actor)
    pack(db, kit, kit_types["CBL"], shelf, actor, count=3)

    status = kits_service.status(db, kit)
    by_type = {line.item_type.code: line for line in status.lines}

    assert by_type["BS"].is_satisfied
    assert by_type["ANT"].missing == 1
    assert by_type["CBL"].missing == 3
    assert status.missing_total == 4
    assert not status.is_complete


def test_spares_in_storage_are_suggested_for_missing_positions(
    db, kit, kit_types, shelf, actor
):
    spare = make_item(db, kit_types["ANT"], name="Антенна на складе", at=LocationRef.storage(shelf.id))

    status = kits_service.status(db, kit)
    antenna_line = next(line for line in status.lines if line.item_type.code == "ANT")

    assert [item.id for item in antenna_line.spares] == [spare.id]


def test_fully_packed_kit_is_complete(db, kit, kit_types, shelf, actor):
    pack(db, kit, kit_types["BS"], shelf, actor)
    pack(db, kit, kit_types["ANT"], shelf, actor, count=2)
    pack(db, kit, kit_types["CBL"], shelf, actor, count=6)

    status = kits_service.status(db, kit)

    assert status.is_complete
    assert status.missing_total == 0
    assert status.unexpected == []


def test_parts_beyond_the_template_are_reported_separately(
    db, kit, kit_types, types, shelf, actor
):
    pack(db, kit, types["RAM"], shelf, actor)

    status = kits_service.status(db, kit)

    assert [item.type.code for item in status.unexpected] == ["RAM"]


def test_uninstall_takes_one_part_out(db, kit, kit_types, shelf, other_shelf, actor):
    part = pack(db, kit, kit_types["ANT"], shelf, actor)[0]

    movements_service.uninstall_component(
        db, item=part, to=LocationRef.storage(other_shelf.id), actor=actor
    )

    assert part.loc_kind is LocationKind.STORAGE
    assert part.loc_storage_place_id == other_shelf.id
    assert tree.contents(db, kit) == []


def test_uninstall_of_a_free_item_is_rejected(db, types, shelf, other_shelf, actor):
    item = make_item(db, types["RAM"], at=LocationRef.storage(shelf.id))

    with pytest.raises(MoveError):
        movements_service.uninstall_component(
            db, item=item, to=LocationRef.storage(other_shelf.id), actor=actor
        )


def test_disassemble_empties_the_kit_and_logs_every_part(
    db, kit, kit_types, shelf, other_shelf, actor
):
    pack(db, kit, kit_types["ANT"], shelf, actor, count=2)
    pack(db, kit, kit_types["CBL"], shelf, actor, count=3)

    taken = movements_service.disassemble(
        db, container=kit, to=LocationRef.storage(other_shelf.id), actor=actor, comment="Разбор"
    )

    assert len(taken) == 5
    assert tree.contents(db, kit) == []
    assert kits_service.status(db, kit).missing_total == 9


def test_kit_travels_as_one_unit(db, kit, kit_types, shelf, employee, actor):
    """Contents are not re-recorded when the kit moves: «inside the kit» is still true."""
    part = pack(db, kit, kit_types["BS"], shelf, actor)[0]
    before = len(movements_service.history(db, part))

    movements_service.issue_item(db, item=kit, employee_id=employee.id, actor=actor)

    assert part.loc_kind is LocationKind.INSIDE
    assert part.loc_parent_item_id == kit.id
    assert len(movements_service.history(db, part)) == before
    # and the part is physically wherever the kit is
    assert tree.outermost(db, part).id == kit.id
    assert kit.loc_employee_id == employee.id


def test_written_off_kit_is_left_out_of_the_report(db, kit, actor):
    movements_service.write_off_item(db, item=kit, actor=actor)

    assert kits_service.all_kits(db) == []
    assert kit.status is ItemStatus.WRITTEN_OFF
