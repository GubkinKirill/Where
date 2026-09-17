from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import app.services  # noqa: F401  registers the placement guard on all sessions
from app.auth.deps import AccessDenied, AuthRequired, NoEmployeeLinked, get_current_user
from app.config import APP_DIR, settings
from app.routers import (
    auth,
    cabinet,
    consumables,
    dashboard,
    directories,
    employees,
    help,
    items,
    kits,
    movements,
    projects,
    reports,
    requests as requests_router,
    self_service,
    storage,
    trips,
    users,
)
from app.templating import render

settings.prepare_dirs()

app = FastAPI(title="Учёт техники", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(items.router)
app.include_router(movements.router)
app.include_router(trips.router)
app.include_router(projects.router)
app.include_router(employees.router)
app.include_router(kits.router)
app.include_router(consumables.router)
app.include_router(storage.router)
app.include_router(reports.router)
app.include_router(requests_router.router)
app.include_router(cabinet.router)
app.include_router(users.router)
app.include_router(self_service.router)
app.include_router(help.router)
app.include_router(directories.router)


@app.exception_handler(AuthRequired)
def handle_auth_required(request: Request, exc: AuthRequired) -> RedirectResponse:
    return RedirectResponse(f"/login?next={request.url.path}", status_code=303)


@app.exception_handler(AccessDenied)
def handle_access_denied(request: Request, exc: AccessDenied) -> HTMLResponse:
    """An employee account that wandered onto an accounting page is sent back to
    its cabinet rather than told off in terms it cannot act on."""
    return render(
        request,
        "forbidden.html",
        {"user": _user_of(request), "required": exc.required},
        status_code=403,
    )


@app.exception_handler(NoEmployeeLinked)
def handle_no_employee(request: Request, exc: NoEmployeeLinked) -> HTMLResponse:
    return render(request, "cabinet/unlinked.html", {"user": _user_of(request)}, status_code=404)


@app.exception_handler(RequestValidationError)
def handle_bad_request(request: Request, exc: RequestValidationError) -> HTMLResponse:
    """A mistyped address — /items/abc — is a page that is not there, not a stack
    of validation JSON the person who typed it can do anything with."""
    return render(request, "not_found.html", {"user": _user_of(request)}, status_code=404)


@app.get("/")
def index(request: Request) -> RedirectResponse:
    """Everyone lands where their work is: the department on the summary,
    an employee in their own cabinet."""
    user = _user_of(request)
    if user is not None and not user.is_staff:
        return RedirectResponse("/cabinet", status_code=303)
    return RedirectResponse("/dashboard", status_code=303)


def _user_of(request: Request):
    """Exception handlers run outside the dependency tree and open their own session."""
    from app.db import SessionLocal

    with SessionLocal() as db:
        return get_current_user(request, db)
