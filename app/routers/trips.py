"""Trips: pack the equipment, follow it while it is away, account for it on return."""

from datetime import datetime, time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.auth.deps import AdminUser, DbSession, EditorUser, ViewerUser
from app.models.base import now
from app.models.directory import Employee
from app.models.item import Item
from app.routers.helpers import date_or_none, form_choices, int_or_none, location_from_form
from app.services import employees as employees_service
from app.services import items as items_service
from app.services import projects as projects_service
from app.services import trips as trips_service
from app.services.errors import ServiceError
from app.templating import redirect, render

router = APIRouter()


@router.get("/trips", response_class=HTMLResponse)
def trip_list(request: Request, db: DbSession, user: ViewerUser) -> HTMLResponse:
    include_closed = request.query_params.get("closed") == "1"
    trips = trips_service.list_trips(db, include_closed=include_closed)
    return render(
        request,
        "trips/list.html",
        {
            "user": user,
            "trips": trips,
            "include_closed": include_closed,
            "counts": {trip.id: len(trips_service.items_in_trip(db, trip)) for trip in trips},
            "away_total": trips_service.count_away(db),
        },
    )


@router.get("/trips/new", response_class=HTMLResponse)
def new_trip_form(request: Request, db: DbSession, user: EditorUser) -> HTMLResponse:
    return render(
        request,
        "trips/form.html",
        {"user": user, "trip": None, "values": {}, **_choices(db)},
    )


@router.post("/trips/new")
async def create_trip(request: Request, db: DbSession, user: EditorUser):
    form = await request.form()
    try:
        employee = employees_service.get_employee(db, int_or_none(form.get("employee_id")) or 0)
        if employee is None:
            raise ServiceError("Выберите сотрудника, который едет.")
        departs_on = date_or_none(form.get("departs_on"))
        if departs_on is None:
            raise ServiceError("Укажите дату выезда.")
        trip = trips_service.create_trip(
            db,
            employee=employee,
            destination=form.get("destination") or "",
            departs_on=departs_on,
            returns_on=date_or_none(form.get("returns_on")),
            purpose=form.get("purpose"),
            project_id=int_or_none(form.get("project_id")),
            notes=form.get("notes"),
        )
    except ServiceError as exc:
        db.rollback()
        return render(
            request,
            "trips/form.html",
            {"user": user, "trip": None, "values": dict(form), "error": str(exc), **_choices(db)},
            status_code=400,
        )

    db.commit()
    return redirect(
        f"/trips/{trip.id}/take",
        flash=f"Командировка {trip.code} создана. Отметьте, что берут с собой.",
    )


@router.get("/trips/{trip_id}", response_class=HTMLResponse)
def trip_card(trip_id: int, request: Request, db: DbSession, user: ViewerUser):
    trip = trips_service.get_trip(db, trip_id)
    if trip is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "trips/card.html",
        {
            "user": user,
            "trip": trip,
            "lines": trips_service.lines(db, trip),
            "away": trips_service.items_in_trip(db, trip),
        },
    )


@router.get("/trips/{trip_id}/edit", response_class=HTMLResponse)
def edit_trip_form(trip_id: int, request: Request, db: DbSession, user: EditorUser):
    trip = trips_service.get_trip(db, trip_id)
    if trip is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "trips/form.html",
        {"user": user, "trip": trip, "values": _values(trip), **_choices(db)},
    )


@router.post("/trips/{trip_id}/edit")
async def edit_trip(trip_id: int, request: Request, db: DbSession, user: EditorUser):
    trip = trips_service.get_trip(db, trip_id)
    if trip is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    try:
        departs_on = date_or_none(form.get("departs_on"))
        if departs_on is None:
            raise ServiceError("Укажите дату выезда.")
        trips_service.update_trip(
            db,
            trip=trip,
            destination=form.get("destination") or "",
            departs_on=departs_on,
            returns_on=date_or_none(form.get("returns_on")),
            purpose=form.get("purpose"),
            project_id=int_or_none(form.get("project_id")),
            notes=form.get("notes"),
        )
    except ServiceError as exc:
        db.rollback()
        return render(
            request,
            "trips/form.html",
            {"user": user, "trip": trip, "values": dict(form), "error": str(exc), **_choices(db)},
            status_code=400,
        )

    db.commit()
    return redirect(f"/trips/{trip.id}", flash="Командировка сохранена.")


@router.get("/trips/{trip_id}/take", response_class=HTMLResponse)
def take_form(trip_id: int, request: Request, db: DbSession, user: EditorUser):
    trip = trips_service.get_trip(db, trip_id)
    if trip is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "trips/take.html",
        {"user": user, "trip": trip, "candidates": trips_service.candidates(db, trip)},
    )


@router.post("/trips/{trip_id}/take")
async def take(trip_id: int, request: Request, db: DbSession, user: EditorUser):
    trip = trips_service.get_trip(db, trip_id)
    if trip is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    chosen = [items_service.get_item(db, int(raw)) for raw in form.getlist("item_id") if raw]
    try:
        moved = trips_service.take_items(
            db,
            trip=trip,
            items=[item for item in chosen if item is not None],
            actor=user,
            comment=form.get("comment"),
        )
    except ServiceError as exc:
        db.rollback()
        return render(
            request,
            "trips/take.html",
            {
                "user": user,
                "trip": trip,
                "candidates": trips_service.candidates(db, trip),
                "error": str(exc),
            },
            status_code=400,
        )

    db.commit()
    return redirect(
        f"/trips/{trip.id}",
        flash=f"Взято в командировку единиц: {len(moved)}. Каждая записана в журнал.",
    )


@router.get("/trips/{trip_id}/return/{item_id}", response_class=HTMLResponse)
def return_form(trip_id: int, item_id: int, request: Request, db: DbSession, user: EditorUser):
    trip, item = _trip_and_item(db, trip_id, item_id)
    if trip is None or item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "trips/return.html",
        {"user": user, "trip": trip, "item": item, **form_choices(db)},
    )


@router.post("/trips/{trip_id}/return/{item_id}")
async def return_from_trip(
    trip_id: int, item_id: int, request: Request, db: DbSession, user: EditorUser
):
    trip, item = _trip_and_item(db, trip_id, item_id)
    if trip is None or item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    try:
        returned_on = date_or_none(form.get("returned_on"))
        trips_service.return_item(
            db,
            trip=trip,
            item=item,
            to=location_from_form(db, form),
            actor=user,
            comment=form.get("comment"),
            moved_at=datetime.combine(returned_on, time(9, 0)) if returned_on else None,
        )
    except ServiceError as exc:
        db.rollback()
        return render(
            request,
            "trips/return.html",
            {"user": user, "trip": trip, "item": item, "error": str(exc), **form_choices(db)},
            status_code=400,
        )

    db.commit()
    return redirect(f"/trips/{trip.id}", flash=f"{item.inv_number} принята из командировки.")


@router.get("/trips/{trip_id}/leave/{item_id}", response_class=HTMLResponse)
def leave_form(trip_id: int, item_id: int, request: Request, db: DbSession, user: EditorUser):
    trip, item = _trip_and_item(db, trip_id, item_id)
    if trip is None or item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(request, "trips/leave.html", {"user": user, "trip": trip, "item": item})


@router.post("/trips/{trip_id}/leave/{item_id}")
async def leave(trip_id: int, item_id: int, request: Request, db: DbSession, user: EditorUser):
    trip, item = _trip_and_item(db, trip_id, item_id)
    if trip is None or item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    try:
        trips_service.leave_item(
            db,
            trip=trip,
            item=item,
            note=form.get("note"),
            actor=user,
            comment=form.get("comment"),
        )
    except ServiceError as exc:
        db.rollback()
        return render(
            request,
            "trips/leave.html",
            {"user": user, "trip": trip, "item": item, "error": str(exc)},
            status_code=400,
        )

    db.commit()
    return redirect(
        f"/trips/{trip.id}", flash=f"{item.inv_number} отмечена оставленной на месте."
    )


@router.post("/trips/{trip_id}/close")
def close(trip_id: int, db: DbSession, user: EditorUser):
    trip = trips_service.get_trip(db, trip_id)
    if trip is None:
        return redirect("/trips", flash="Командировка не найдена.", kind="warn")
    try:
        trips_service.close_trip(db, trip=trip)
    except ServiceError as exc:
        db.rollback()
        return redirect(f"/trips/{trip_id}", flash=str(exc), kind="warn")
    db.commit()
    return redirect(f"/trips/{trip_id}", flash=f"Командировка {trip.code} закрыта.")


@router.post("/trips/{trip_id}/reopen")
def reopen(trip_id: int, db: DbSession, user: EditorUser):
    trip = trips_service.get_trip(db, trip_id)
    if trip is None:
        return redirect("/trips", flash="Командировка не найдена.", kind="warn")
    trips_service.reopen_trip(db, trip=trip)
    db.commit()
    return redirect(f"/trips/{trip_id}", flash="Командировка снова открыта.")


@router.post("/trips/{trip_id}/delete")
def delete(trip_id: int, db: DbSession, user: AdminUser):
    trip = trips_service.get_trip(db, trip_id)
    if trip is None:
        return redirect("/trips", flash="Командировка не найдена.", kind="warn")
    code = trip.code
    try:
        trips_service.delete_trip(db, trip=trip)
    except ServiceError as exc:
        db.rollback()
        return redirect(f"/trips/{trip_id}", flash=str(exc), kind="warn")
    db.commit()
    return redirect("/trips", flash=f"Командировка {code} удалена.")


@router.get("/trips/{trip_id}/act", response_class=HTMLResponse)
def trip_act(trip_id: int, request: Request, db: DbSession, user: ViewerUser):
    """Printable list of what the traveller signed for."""
    trip = trips_service.get_trip(db, trip_id)
    if trip is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "reports/act.html",
        {
            "user": user,
            "title": f"Оборудование в командировку {trip.code}",
            "subtitle": f"{trip.destination} · выезд {trip.departs_on.strftime('%d.%m.%Y')}",
            "employee": trip.employee,
            "items": [line.item for line in trips_service.lines(db, trip)],
            "issued_at": now(),
            "back_url": f"/trips/{trip.id}",
        },
    )


@router.get("/items/{item_id}/to-trip", response_class=HTMLResponse)
def send_form(item_id: int, request: Request, db: DbSession, user: EditorUser):
    """«В командировку» straight from the unit's card."""
    item = items_service.get_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "trips/send.html",
        {"user": user, "item": item, "trips": trips_service.open_trips(db)},
    )


@router.post("/items/{item_id}/to-trip")
async def send(item_id: int, request: Request, db: DbSession, user: EditorUser):
    item = items_service.get_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    trip = trips_service.get_trip(db, int_or_none(form.get("trip_id")) or 0)
    try:
        if trip is None:
            raise ServiceError("Выберите командировку.")
        trips_service.take_items(
            db, trip=trip, items=[item], actor=user, comment=form.get("comment")
        )
    except ServiceError as exc:
        db.rollback()
        return render(
            request,
            "trips/send.html",
            {
                "user": user,
                "item": item,
                "trips": trips_service.open_trips(db),
                "error": str(exc),
            },
            status_code=400,
        )

    db.commit()
    return redirect(
        f"/items/{item.id}", flash=f"{item.inv_number} уехала с командировкой {trip.code}."
    )


# --- internals ---------------------------------------------------------------


def _choices(db: DbSession) -> dict:
    return {
        "employees": list(
            db.scalars(select(Employee).where(Employee.is_active).order_by(Employee.full_name))
        ),
        "projects": projects_service.list_projects(db, include_closed=False),
    }


def _values(trip) -> dict:
    return {
        "employee_id": trip.employee_id,
        "destination": trip.destination,
        "purpose": trip.purpose or "",
        "project_id": trip.project_id or "",
        "departs_on": trip.departs_on.isoformat(),
        "returns_on": trip.returns_on.isoformat() if trip.returns_on else "",
        "notes": trip.notes or "",
    }


def _trip_and_item(db: DbSession, trip_id: int, item_id: int) -> tuple:
    trip = trips_service.get_trip(db, trip_id)
    item = db.get(Item, item_id)
    return trip, item
