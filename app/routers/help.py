"""In-app documentation. Open without signing in: it explains the system to someone
who has not got an account yet, and to employees who never will have one."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth.deps import CurrentUser
from app.templating import render

router = APIRouter()

# slug -> title, in the order they appear in the sidebar
PAGES: list[tuple[str, str]] = [
    ("index", "С чего начать"),
    ("items", "Единицы учёта"),
    ("movements", "Перемещения"),
    ("kits", "Состав и комплекты"),
    ("employees", "Сотрудники"),
    ("self", "Для сотрудника"),
    ("admin", "Администратору"),
]

TITLES = dict(PAGES)


@router.get("/help", response_class=HTMLResponse)
def help_index(request: Request, user: CurrentUser) -> HTMLResponse:
    return _page(request, user, "index")


@router.get("/help/{slug}", response_class=HTMLResponse)
def help_page(slug: str, request: Request, user: CurrentUser) -> HTMLResponse:
    if slug not in TITLES:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return _page(request, user, slug)


def _page(request: Request, user, slug: str) -> HTMLResponse:
    return render(
        request,
        f"help/{slug}.html",
        {"user": user, "pages": PAGES, "page": slug, "page_title": TITLES[slug]},
    )
