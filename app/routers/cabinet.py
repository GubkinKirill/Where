"""The employee's own cabinet: signed in as themselves, they see what is assigned
to them, confirm handovers and look up colleagues.

Read only by construction — nothing here writes a location. The one thing an
employee may change is their own acknowledgement of a handover.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth.deps import CabinetUser, DbSession
from app.models.base import now
from app.models.directory import Employee
from app.models.movement import Movement
from app.routers.helpers import int_or_none
from app.schemas.item import ItemFilter
from app.services import consumables as consumables_service
from app.services import employees as employees_service
from app.services import items as items_service
from app.services import movements as movements_service
from app.services import tree
from app.services import trips as trips_service
from app.services.errors import ServiceError
from app.templating import redirect, render

router = APIRouter()


@router.get("/cabinet", response_class=HTMLResponse)
def cabinet(request: Request, db: DbSession, user: CabinetUser) -> HTMLResponse:
    employee = user.employee
    held = employees_service.items_of(db, employee)
    return render(
        request,
        "cabinet/index.html",
        {
            "user": user,
            "employee": employee,
            "items": held,
            "contents": {item.id: tree.contents(db, item) for item in held},
            "open_issues": {item.id: movements_service.open_issue(db, item) for item in held},
            "pending": movements_service.pending_acknowledgements(db, employee),
            "consumables": consumables_service.issued_to(db, employee, limit=10),
            "trips": trips_service.open_trips_of(db, employee),
            "away": trips_service.items_away_with(db, employee),
        },
    )


@router.post("/cabinet/confirm")
async def confirm(request: Request, db: DbSession, user: CabinetUser):
    """«Получил» — the same acknowledgement as on /my, only signed in."""
    form = await request.form()
    movement = db.get(Movement, int_or_none(form.get("movement_id")) or 0)
    if movement is None:
        return redirect("/cabinet", flash="Запись о выдаче не найдена.", kind="warn")
    try:
        movements_service.acknowledge(db, movement=movement, employee=user.employee)
    except ServiceError as exc:
        db.rollback()
        return redirect("/cabinet", flash=str(exc), kind="warn")
    db.commit()
    return redirect("/cabinet", flash=f"Получение {movement.item.inv_number} подтверждено.")


@router.get("/cabinet/history", response_class=HTMLResponse)
def history(request: Request, db: DbSession, user: CabinetUser) -> HTMLResponse:
    """Everything ever handed to this person or taken back from them."""
    return render(
        request,
        "cabinet/history.html",
        {
            "user": user,
            "employee": user.employee,
            "movements": employees_service.history_of(db, user.employee),
        },
    )


@router.get("/cabinet/act", response_class=HTMLResponse)
def own_act(request: Request, db: DbSession, user: CabinetUser) -> HTMLResponse:
    """The printable list of one's own equipment — the paper you sign."""
    return render(
        request,
        "reports/act.html",
        {
            "user": user,
            "title": "Акт закрепления оборудования",
            "employee": user.employee,
            "items": employees_service.items_of(db, user.employee),
            "issued_at": now(),
            "back_url": "/cabinet",
        },
    )


@router.get("/cabinet/colleagues", response_class=HTMLResponse)
def colleagues(request: Request, db: DbSession, user: CabinetUser) -> HTMLResponse:
    """Who else holds what. Names, departments and counts — no personal details,
    the same thing anybody could see by walking round the offices."""
    query = (request.query_params.get("q") or "").strip()
    people = employees_service.with_counts(db, query=query or None)
    return render(
        request,
        "cabinet/colleagues.html",
        {"user": user, "employee": user.employee, "people": people, "q": query},
    )


@router.get("/cabinet/colleagues/{employee_id}", response_class=HTMLResponse)
def colleague(
    employee_id: int, request: Request, db: DbSession, user: CabinetUser
) -> HTMLResponse:
    person = db.get(Employee, employee_id)
    if person is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    held = employees_service.items_of(db, person)
    return render(
        request,
        "cabinet/colleague.html",
        {
            "user": user,
            "employee": user.employee,
            "person": person,
            "items": held,
            "contents": {item.id: tree.contents(db, item) for item in held},
        },
    )


@router.get("/cabinet/search", response_class=HTMLResponse)
def search(request: Request, db: DbSession, user: CabinetUser) -> HTMLResponse:
    """«Чей это монитор» — look a unit up by the number on its sticker."""
    query = (request.query_params.get("q") or "").strip()
    found = (
        items_service.search_items(db, ItemFilter(q=query, limit=50)) if query else []
    )
    return render(
        request,
        "cabinet/search.html",
        {"user": user, "employee": user.employee, "q": query, "items": found},
    )
