from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import app.services  # noqa: F401  registers the placement guard on all sessions
from app.auth.deps import AccessDenied, AuthRequired
from app.config import APP_DIR, settings
from app.routers import (
    auth,
    directories,
    employees,
    items,
    kits,
    movements,
    reports,
    self_service,
)
from app.templating import render

settings.prepare_dirs()

app = FastAPI(title="Учёт техники", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

app.include_router(auth.router)
app.include_router(items.router)
app.include_router(movements.router)
app.include_router(employees.router)
app.include_router(kits.router)
app.include_router(reports.router)
app.include_router(self_service.router)
app.include_router(directories.router)


@app.exception_handler(AuthRequired)
def handle_auth_required(request: Request, exc: AuthRequired) -> RedirectResponse:
    return RedirectResponse(f"/login?next={request.url.path}", status_code=303)


@app.exception_handler(AccessDenied)
def handle_access_denied(request: Request, exc: AccessDenied) -> HTMLResponse:
    return render(request, "forbidden.html", {"required": exc.required}, status_code=403)


@app.get("/")
def index() -> RedirectResponse:
    return RedirectResponse("/items", status_code=303)
