"""End to end through HTTP: sign in, look at a card, hand an item over."""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth.providers import hash_password
from app.db import get_db
from app.main import app
from app.models.enums import ItemStatus, LocationKind, UserRole
from app.models.user import User
from app.services.location import LocationRef
from tests.factories import make_item


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def editor(db) -> User:
    user = User(
        username="editor",
        full_name="Редактор",
        role=UserRole.EDITOR,
        password_hash=hash_password("secret12345"),
    )
    db.add(user)
    db.flush()
    return user


def sign_in(client, username="editor", password="secret12345"):
    response = client.post(
        "/login", data={"username": username, "password": password}, follow_redirects=False
    )
    assert response.status_code == 303
    return response


def test_anonymous_is_redirected_to_login(client):
    response = client.get("/items", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/items"


def test_wrong_password_is_refused(client, editor):
    response = client.post("/login", data={"username": "editor", "password": "nope"})
    assert response.status_code == 401


def test_list_and_card(client, db, editor, types, shelf):
    item = make_item(db, types["PC"], name="Системный блок HP", at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "editor")

    listing = client.get("/items")
    assert listing.status_code == 200
    assert item.inv_number in listing.text

    card = client.get(f"/items/{item.id}")
    assert card.status_code == 200
    assert "Системный блок HP" in card.text
    assert "Полка 1" in card.text


def test_search_filters_the_list(client, db, editor, types, shelf):
    make_item(db, types["PC"], name="Системный блок HP", at=LocationRef.storage(shelf.id))
    make_item(db, types["MON"], name="Монитор Dell", at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "editor")

    found = client.get("/items", params={"q": "Монитор"})
    assert "Монитор Dell" in found.text
    assert "Системный блок HP" not in found.text


def test_issue_through_the_web_form(client, db, editor, types, shelf, employee):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "editor")

    response = client.post(
        f"/items/{item.id}/issue",
        data={"loc_kind": "person", "employee_id": str(employee.id)},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db.refresh(item)
    assert item.loc_kind is LocationKind.PERSON
    assert item.loc_employee_id == employee.id
    assert item.status is ItemStatus.IN_USE


def test_viewer_cannot_open_the_issue_form(client, db, types, shelf):
    viewer = User(
        username="viewer",
        role=UserRole.VIEWER,
        password_hash=hash_password("secret12345"),
    )
    db.add(viewer)
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "viewer")

    response = client.get(f"/items/{item.id}/issue")
    assert response.status_code == 403


def test_search_ignores_case_in_russian(client, db, editor, types, shelf):
    """SQLite folds ASCII only — app.db replaces lower() so «монитор» finds «Монитор»."""
    item = make_item(db, types["MON"], name="Монитор Dell", at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "editor")

    found = client.get("/items", params={"q": "монитор"}).text
    assert item.inv_number in found


def test_a_mistyped_address_shows_the_not_found_page(client, db, editor, types, shelf):
    """/items/abc is a page that is not there, not a page of validation JSON."""
    db.commit()
    sign_in(client, "editor")

    response = client.get("/items/abc")

    assert response.status_code == 404
    assert response.text.lstrip().lower().startswith("<!doctype")


def test_an_unreadable_filter_still_shows_the_list(client, db, editor, types, shelf):
    """A stale bookmark must not take the whole list down."""
    item = make_item(db, types["MON"], name="Монитор Dell", at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "editor")

    response = client.get("/items", params={"status": "такого-статуса-нет"})

    assert response.status_code == 200
    assert item.inv_number in response.text
    assert "Фильтр не понят" in response.text


def test_the_summary_offers_no_new_item_button_to_a_viewer(client, db, types, shelf):
    viewer = User(
        username="viewer",
        role=UserRole.VIEWER,
        password_hash=hash_password("secret12345"),
    )
    db.add(viewer)
    db.commit()
    sign_in(client, "viewer")

    assert "/items/new" not in client.get("/dashboard").text


def test_the_section_bar_stays_one_line(client, db, editor, types, shelf):
    """Шапка не должна становиться двухэтажной: полоса разделов рассчитана
    на пять вкладок, всё остальное живёт в «Ещё»."""
    db.commit()
    sign_in(client, "editor")

    html = client.get("/items").text
    bar = html[html.index('<nav class="nav">') : html.index("</nav>")]
    tabs = re.findall(r">([^<>]+)</a>", bar)

    assert len(tabs) <= 5, f"вкладок стало {len(tabs)}: {tabs}"
    assert "Командировки" in "".join(tabs)

    menu = html[html.index("menu__list") : html.index("</details>")]
    assert "Проекты" in menu and "Комплекты" in menu


def test_global_search_opens_the_only_match(client, db, editor, types, shelf):
    item = make_item(db, types["PC"], name="Системный блок HP", at=LocationRef.storage(shelf.id))
    make_item(db, types["MON"], name="Монитор Dell", at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "editor")

    # точный инвентарный номер — сразу карточка, даже набранный строчными
    exact = client.get("/find", params={"q": item.inv_number.lower()}, follow_redirects=False)
    assert exact.status_code == 303
    assert exact.headers["location"] == f"/items/{item.id}"

    # единственное совпадение по названию — тоже карточка
    single = client.get("/find", params={"q": "Системный"}, follow_redirects=False)
    assert single.headers["location"] == f"/items/{item.id}"

    # несколько совпадений — список с тем же запросом
    many = client.get("/find", params={"q": "о"}, follow_redirects=False)
    assert many.headers["location"].startswith("/items?q=")

    # пустой запрос никуда не ведёт, кроме списка
    empty = client.get("/find", params={"q": "  "}, follow_redirects=False)
    assert empty.headers["location"] == "/items"


def test_journal_page_filters_what_it_shows(client, db, editor, types, shelf, employee):
    kept = make_item(db, types["PC"], name="Нужная единица", at=LocationRef.storage(shelf.id))
    hidden = make_item(db, types["MON"], name="Лишняя единица", at=LocationRef.storage(shelf.id))
    db.commit()
    sign_in(client, "editor")

    page = client.get("/movements", params={"q": kept.inv_number})

    assert kept.inv_number in page.text
    assert hidden.inv_number not in page.text
    assert "Сбросить" in page.text


def test_the_list_offers_the_next_action_and_flags_overdue(
    client, db, editor, types, shelf, employee
):
    from datetime import date, timedelta

    from app.services import movements as movements_service

    spare = make_item(db, types["MON"], name="Монитор на полке", at=LocationRef.storage(shelf.id))
    issued = make_item(db, types["PC"], name="Блок у человека", at=LocationRef.storage(shelf.id))
    movements_service.issue_item(
        db,
        item=issued,
        employee_id=employee.id,
        expected_return_date=date.today() - timedelta(days=2),
    )
    db.commit()
    sign_in(client, "editor")

    page = client.get("/items").text

    assert f'/items/{spare.id}/issue">Выдать' in page
    assert f'/items/{issued.id}/return">Принять' in page
    assert "возврат просрочен" in page
