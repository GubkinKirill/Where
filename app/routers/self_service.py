"""Self service for people without an account: «what is assigned to me».

Opens without a login — the employee identifies themselves with the number printed
on their pass. That is identification, not authentication: anyone who knows the
number sees the list, so this page shows only equipment, nothing else about the
person, and it never puts the number into a URL.
"""

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.auth.deps import DbSession
from app.models.directory import Employee
from app.models.movement import Movement
from app.routers.helpers import int_or_none
from app.services import employees as employees_service
from app.services import movements as movements_service
from app.services import tree
from app.services.errors import ServiceError
from app.templating import render

router = APIRouter()


@router.get("/my", response_class=HTMLResponse)
def enter_number(request: Request) -> HTMLResponse:
    return render(request, "self/enter.html", {})


@router.post("/my", response_class=HTMLResponse)
async def show_my_items(request: Request, db: DbSession) -> HTMLResponse:
    form = await request.form()
    number = (form.get("personnel_number") or "").strip()
    employee = _find(db, number)
    if employee is None:
        return render(
            request,
            "self/enter.html",
            {"error": "Сотрудник с таким табельным номером не найден."},
            status_code=404,
        )
    return _render_items(request, db, employee, number)


@router.post("/my/confirm", response_class=HTMLResponse)
async def confirm_handover(request: Request, db: DbSession) -> HTMLResponse:
    """The recipient confirms, with the number on their pass, that they got the item."""
    form = await request.form()
    number = (form.get("personnel_number") or "").strip()
    employee = _find(db, number)
    if employee is None:
        return render(
            request,
            "self/enter.html",
            {"error": "Сотрудник с таким табельным номером не найден."},
            status_code=404,
        )

    message, kind = None, "ok"
    movement = db.get(Movement, int_or_none(form.get("movement_id")) or 0)
    if movement is None:
        message, kind = "Запись о выдаче не найдена.", "warn"
    else:
        try:
            movements_service.acknowledge(db, movement=movement, employee=employee)
            db.commit()
            message = f"Получение {movement.item.inv_number} подтверждено."
        except ServiceError as exc:
            db.rollback()
            message, kind = str(exc), "warn"

    return _render_items(request, db, employee, number, message=message, kind=kind)


# --- internals ---------------------------------------------------------------


def _find(db: DbSession, number: str) -> Optional[Employee]:
    if not number:
        return None
    return db.scalars(select(Employee).where(Employee.personnel_number == number)).first()


def _render_items(
    request: Request,
    db: DbSession,
    employee: Employee,
    number: str,
    *,
    message: Optional[str] = None,
    kind: str = "ok",
) -> HTMLResponse:
    held = employees_service.items_of(db, employee)
    return render(
        request,
        "self/items.html",
        {
            "employee": employee,
            "personnel_number": number,
            "items": held,
            "contents": {item.id: tree.contents(db, item) for item in held},
            "open_issues": {
                item.id: movements_service.open_issue(db, item) for item in held
            },
            "pending": movements_service.pending_acknowledgements(db, employee),
            "flash": {"kind": kind, "text": message} if message else None,
        },
    )
