from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth.deps import DbSession, ViewerUser
from app.models.base import now
from app.models.movement import Movement
from app.services import employees as employees_service
from app.services import movements as movements_service
from app.templating import render

router = APIRouter()


@router.get("/reports/unconfirmed", response_class=HTMLResponse)
def unconfirmed(request: Request, db: DbSession, user: ViewerUser) -> HTMLResponse:
    """Handed out but never confirmed by the person who took it."""
    pending = movements_service.unacknowledged(db)
    return render(
        request,
        "reports/unconfirmed.html",
        {
            "user": user,
            "movements": pending,
            "today": now(),
        },
    )


@router.get("/employees/{employee_id}/act", response_class=HTMLResponse)
def employee_act(employee_id: int, request: Request, db: DbSession, user: ViewerUser):
    """Printable list of everything assigned to a person, with a place to sign."""
    employee = employees_service.get_employee(db, employee_id)
    if employee is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "reports/act.html",
        {
            "user": user,
            "title": "Акт закрепления оборудования",
            "employee": employee,
            "items": employees_service.items_of(db, employee),
            "issued_at": now(),
        },
    )


@router.get("/movements/{movement_id}/act", response_class=HTMLResponse)
def movement_act(movement_id: int, request: Request, db: DbSession, user: ViewerUser):
    """Printable act for one particular handover."""
    movement = db.get(Movement, movement_id)
    if movement is None or movement.recipient is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "reports/act.html",
        {
            "user": user,
            "title": "Акт приёма-передачи",
            "employee": movement.recipient,
            "items": [movement.item],
            "movement": movement,
            "issued_at": movement.moved_at,
        },
    )
