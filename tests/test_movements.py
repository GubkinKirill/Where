import pytest

from app.models.enums import ItemStatus, LocationKind, MovementReason
from app.services import movements as movements_service
from app.services import tree
from app.services.errors import MoveError
from app.services.location import LocationRef
from tests.factories import make_item


def test_move_updates_cache_and_writes_history(db, types, shelf, other_shelf, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    movements_service.move_item(
        db,
        item=item,
        to=LocationRef.storage(other_shelf.id),
        reason=MovementReason.TO_STORAGE,
        actor=actor,
    )

    assert item.loc_kind is LocationKind.STORAGE
    assert item.loc_storage_place_id == other_shelf.id

    log = movements_service.history(db, item)
    assert [record.reason for record in log] == [
        MovementReason.TO_STORAGE,
        MovementReason.REGISTER,
    ]
    assert log[0].from_storage_place_id == shelf.id
    assert log[0].from_label == "склад · Полка 1"
    assert log[0].to_label == "склад · Полка 2"
    assert log[0].moved_by_user_id == actor.id


def test_moving_to_the_same_place_is_rejected(db, types, shelf, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    with pytest.raises(MoveError):
        movements_service.move_item(
            db,
            item=item,
            to=LocationRef.storage(shelf.id),
            reason=MovementReason.TO_STORAGE,
            actor=actor,
        )


def test_issue_takes_room_from_employee_and_return_closes_it(
    db, types, shelf, employee, room, actor
):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)

    assert item.loc_kind is LocationKind.PERSON
    assert item.loc_employee_id == employee.id
    assert item.loc_room_id is None  # only set when explicitly overridden
    assert item.status is ItemStatus.IN_USE

    issue = movements_service.open_issue(db, item)
    assert issue is not None
    assert issue.recipient_employee_id == employee.id

    movements_service.return_to_storage(db, item=item, storage_place_id=shelf.id, actor=actor)

    assert item.loc_kind is LocationKind.STORAGE
    assert item.status is ItemStatus.RESERVE
    assert issue.returned_at is not None
    assert movements_service.open_issue(db, item) is None


def test_issue_with_explicit_room(db, types, shelf, employee, room, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    movements_service.issue_item(
        db, item=item, employee_id=employee.id, room_id=room.id, actor=actor
    )

    assert item.loc_room_id == room.id
    log = movements_service.history(db, item)
    assert log[0].to_label == "Петров И. С., каб. 312"


def test_nesting_and_contents(db, types, shelf, actor):
    at_shelf = LocationRef.storage(shelf.id)
    pc = make_item(db, types["PC"], name="Системный блок", at=at_shelf, actor=actor)
    ram = make_item(db, types["RAM"], name="Планка", at=at_shelf, actor=actor)

    movements_service.move_item(
        db, item=ram, to=LocationRef.inside(pc.id), reason=MovementReason.INSTALL, actor=actor
    )

    assert ram.loc_kind is LocationKind.INSIDE
    assert [child.id for child in tree.contents(db, pc)] == [ram.id]
    assert [parent.id for parent in tree.ancestors(db, ram)] == [pc.id]


def test_item_cannot_be_nested_into_itself(db, types, shelf, actor):
    pc = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    with pytest.raises(MoveError):
        movements_service.move_item(
            db, item=pc, to=LocationRef.inside(pc.id), reason=MovementReason.INSTALL, actor=actor
        )


def test_nesting_cycle_is_rejected_at_any_depth(db, types, shelf, actor):
    at_shelf = LocationRef.storage(shelf.id)
    outer = make_item(db, types["PC"], name="Внешний", at=at_shelf, actor=actor)
    middle = make_item(db, types["PC"], name="Средний", at=at_shelf, actor=actor)
    inner = make_item(db, types["PC"], name="Внутренний", at=at_shelf, actor=actor)

    movements_service.move_item(
        db, item=middle, to=LocationRef.inside(outer.id), reason=MovementReason.INSTALL, actor=actor
    )
    movements_service.move_item(
        db, item=inner, to=LocationRef.inside(middle.id), reason=MovementReason.INSTALL, actor=actor
    )

    # outer would end up inside its own grandchild
    with pytest.raises(MoveError):
        movements_service.move_item(
            db,
            item=outer,
            to=LocationRef.inside(inner.id),
            reason=MovementReason.INSTALL,
            actor=actor,
        )


def test_non_container_cannot_hold_items(db, types, shelf, actor):
    at_shelf = LocationRef.storage(shelf.id)
    ram = make_item(db, types["RAM"], at=at_shelf, actor=actor)
    monitor = make_item(db, types["MON"], at=at_shelf, actor=actor)

    with pytest.raises(MoveError):
        movements_service.move_item(
            db,
            item=ram,
            to=LocationRef.inside(monitor.id),
            reason=MovementReason.INSTALL,
            actor=actor,
        )


def test_write_off_marks_status_and_blocks_further_moves(db, types, shelf, other_shelf, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    movements_service.write_off_item(db, item=item, actor=actor, comment="Не подлежит ремонту")

    assert item.status is ItemStatus.WRITTEN_OFF
    assert item.loc_kind is LocationKind.WRITTEN_OFF
    assert movements_service.history(db, item)[0].reason is MovementReason.WRITE_OFF

    with pytest.raises(MoveError):
        movements_service.move_item(
            db,
            item=item,
            to=LocationRef.storage(other_shelf.id),
            reason=MovementReason.TO_STORAGE,
            actor=actor,
        )


def test_write_off_of_a_container_leaves_contents_in_place(db, types, shelf, actor):
    at_shelf = LocationRef.storage(shelf.id)
    pc = make_item(db, types["PC"], at=at_shelf, actor=actor)
    ram = make_item(db, types["RAM"], at=at_shelf, actor=actor)
    movements_service.move_item(
        db, item=ram, to=LocationRef.inside(pc.id), reason=MovementReason.INSTALL, actor=actor
    )

    movements_service.write_off_item(db, item=pc, actor=actor)

    assert ram.loc_kind is LocationKind.INSIDE
    assert ram.loc_parent_item_id == pc.id
    assert ram.status is not ItemStatus.WRITTEN_OFF
    assert len(movements_service.history(db, ram)) == 2  # register + install, nothing more


def test_journal_narrows_by_reason_person_and_dates(db, types, shelf, employee, actor):
    from datetime import date, timedelta

    from app.schemas.movement import MovementFilter

    item = make_item(db, types["PC"], name="Ноутбук в журнале", at=LocationRef.storage(shelf.id), actor=actor)
    movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)
    other = make_item(db, types["MON"], at=LocationRef.storage(shelf.id), actor=actor)

    everything = movements_service.search(db, MovementFilter())
    by_reason = movements_service.search(db, MovementFilter(reason=MovementReason.ISSUE))
    by_person = movements_service.search(db, MovementFilter(employee_id=employee.id))
    by_number = movements_service.search(db, MovementFilter(q=item.inv_number))
    by_name = movements_service.search(db, MovementFilter(q="ноутбук в журнале"))
    tomorrow = movements_service.search(db, MovementFilter(date_from=date.today() + timedelta(days=1)))
    today = movements_service.search(db, MovementFilter(date_to=date.today()))

    assert len(everything) == 3  # две постановки на учёт и выдача
    assert [record.reason for record in by_reason] == [MovementReason.ISSUE]
    assert all(record.item_id == item.id for record in by_person)
    assert {record.item_id for record in by_number} == {item.id}
    assert by_name and all(record.item_id == item.id for record in by_name)
    assert tomorrow == []
    assert len(today) == 3  # день «по» включительно
    assert other.id not in {record.item_id for record in by_number}


def test_journal_filters_stack(db, types, shelf, employee, actor):
    from app.schemas.movement import MovementFilter

    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)

    narrowed = movements_service.search(
        db, MovementFilter(employee_id=employee.id, reason=MovementReason.REGISTER)
    )

    assert narrowed == []  # постановку на учёт этому человеку не делали
