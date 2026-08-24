"""The front page for the department: what is where, and what needs attention."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth.deps import DbSession, ViewerUser
from app.services import dashboard as dashboard_service
from app.templating import render

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: DbSession, user: ViewerUser) -> HTMLResponse:
    return render(
        request,
        "dashboard.html",
        {"user": user, **dashboard_service.summary(db)},
    )
