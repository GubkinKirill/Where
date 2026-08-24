"""Quantity accounting: the ledger and the quantity must never disagree."""

import pytest

from app.models.consumable import ConsumableStock
from app.models.enums import ConsumableReason
from app.schemas.consumable import ConsumableFilter, ConsumableForm
from app.services import consumables as consumables_service
from app.services.errors import LocationWriteError, ServiceError


def form(name="Патч-корд UTP 2 м", **fields) -> ConsumableForm:
    return ConsumableForm(name=name, **fields)


@pytest.fixture
def stock(db, shelf) -> ConsumableStock:
    return consumables_service.create_stock(
        db,
        form=form(category="Кабели", min_quantity=10, storage_place_id=shelf.id),
        quantity=12,
    )


def test_opening_balance_is_a_ledger_line(db, stock):
    history = consumables_service.history(db, stock)
    assert stock.quantity == 12
    assert len(history) == 1
    assert history[0].reason is ConsumableReason.RECEIPT
    assert history[0].delta == 12
    assert history[0].quantity_after == 12


def test_receipt_and_issue_move_the_quantity(db, stock, employee, actor):
    consumables_service.receive(db, stock=stock, quantity=5, actor=actor, comment="Закупка")
    consumables_service.issue(
        db, stock=stock, quantity=3, employee_id=employee.id, actor=actor
    )
    db.flush()
    assert stock.quantity == 14

    latest = consumables_service.history(db, stock)[0]
    assert latest.delta == -3
    assert latest.quantity_after == 14
    assert latest.employee_id == employee.id


def test_issue_cannot_go_below_zero(db, stock, employee):
    with pytest.raises(ServiceError):
        consumables_service.issue(db, stock=stock, quantity=13, employee_id=employee.id)
    assert stock.quantity == 12


def test_issue_needs_a_recipient_or_a_reason(db, stock):
    with pytest.raises(ServiceError):
        consumables_service.issue(db, stock=stock, quantity=1)
    consumables_service.issue(db, stock=stock, quantity=1, comment="На сборку PC-0014")
    db.flush()
    assert stock.quantity == 11


def test_recount_logs_the_difference(db, stock, actor):
    movement = consumables_service.adjust(db, stock=stock, counted=7, actor=actor)
    db.flush()
    assert stock.quantity == 7
    assert movement.reason is ConsumableReason.ADJUST
    assert movement.delta == -5

    with pytest.raises(ServiceError):
        consumables_service.adjust(db, stock=stock, counted=7)


def test_quantity_cannot_be_changed_behind_the_ledger(db, stock):
    stock.quantity = 99
    with pytest.raises(LocationWriteError):
        db.flush()
    db.rollback()


def test_low_stock_lists_thresholds_and_zeroes(db, shelf):
    low = consumables_service.create_stock(
        db, form=form("Кабель питания C13", min_quantity=5), quantity=2
    )
    empty = consumables_service.create_stock(db, form=form("Переходник HDMI–VGA"), quantity=0)
    plenty = consumables_service.create_stock(
        db, form=form("Мышь USB", min_quantity=3), quantity=10
    )
    db.flush()

    running_out = consumables_service.low_stock(db)
    assert low in running_out and empty in running_out
    assert plenty not in running_out


def test_filters_narrow_the_list(db, shelf, other_shelf):
    cable = consumables_service.create_stock(
        db, form=form("Патч-корд", category="Кабели", storage_place_id=shelf.id), quantity=4
    )
    mouse = consumables_service.create_stock(
        db,
        form=form("Мышь USB", category="Периферия", storage_place_id=other_shelf.id),
        quantity=1,
    )
    db.flush()

    assert consumables_service.search(db, ConsumableFilter(category="Кабели")) == [cable]
    assert consumables_service.search(
        db, ConsumableFilter(storage_place_id=other_shelf.id)
    ) == [mouse]
    assert consumables_service.search(db, ConsumableFilter(q="патч")) == [cable]


def test_used_position_is_not_deleted(db, stock):
    with pytest.raises(ServiceError):
        consumables_service.delete_stock(db, stock=stock)

    untouched = ConsumableStock(name="Ничего не было")
    db.add(untouched)
    db.flush()
    consumables_service.delete_stock(db, stock=untouched)
    assert consumables_service.get_stock(db, untouched.id) is None


def test_issued_to_a_person_is_visible_on_their_card(db, stock, employee, actor):
    consumables_service.issue(
        db, stock=stock, quantity=2, employee_id=employee.id, actor=actor, comment="Монтаж"
    )
    db.flush()
    given = consumables_service.issued_to(db, employee)
    assert len(given) == 1
    assert given[0].delta == -2
