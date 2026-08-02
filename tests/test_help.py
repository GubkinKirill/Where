"""Documentation must open for someone who has no account yet."""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.routers.help import PAGES


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_index_opens_without_signing_in(client):
    response = client.get("/help")
    assert response.status_code == 200
    assert "С чего начать" in response.text


@pytest.mark.parametrize("slug,title", [(slug, title) for slug, title in PAGES])
def test_every_page_renders(client, slug, title):
    url = "/help" if slug == "index" else f"/help/{slug}"
    response = client.get(url)

    assert response.status_code == 200
    assert title in response.text
    # the sidebar links to every other page
    assert 'class="doc-nav"' in response.text


def test_unknown_page_is_not_found(client):
    assert client.get("/help/nonsense").status_code == 404


def test_login_page_points_at_the_documentation(client):
    assert "/help" in client.get("/login").text
