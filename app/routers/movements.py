from datetime import date
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.auth.deps import DbSession, EditorUser, ViewerUser
from app.models.enums import LocationKind, MovementReason
from app.models.item import Item
from app.models.movement import Movement
from app.services import items as items_service
from app.services import movements as movements_service
from app.services import tree
from app.services.errors import ServiceError
from app.routers.helpers import form_choices, int_or_none, location_from_form
from app.templating import redirect, render

router = APIRouter()

# which reason a plain "move" gets when the user does not pick one
DEFAULT_REASONS = {
    LocationKind.INSIDE: MovementReason.INSTALL,
    LocationKind.STORAGE: MovementReason.TO_STORAGE,
    LocationKind.PERSON: MovementReason.ISSUE,
    LocationKind.ROOM: MovementReason.TO_STORAGE,
    LocationKind.EXTERNAL: MovementReason.TRANSFER_OUT,
    LocationKind.WRITTEN_OFF: MovementReason.WRITE_OFF,
}


@router.get("/items/{item_id}/move", response_class=HTMLResponse)
def move_form(item_id: int, request: Request, db: DbSession, user: EditorUser):
    item = _require_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "movements/move.html",
        {"user": user, "item": item, **form_choices(db)},
    )


@router.post("/items/{item_id}/move")
async def move(item_id: int, request: Request, db: DbSession, user: EditorUser):
    item = _require_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    try:
        target = location_from_form(db, form)
        raw_reason = (form.get("reason") or "").strip()
        reason = MovementReason(raw_reason) if raw_reason else DEFAULT_REASONS[target.kind]
        movements_service.move_item(
            db,
            item=item,
            to=target,
            reason=reason,
            actor=user,
            comment=form.get("comment"),
        )
    except ServiceError as exc:
        db.rollback()
        return render(
            request,
            "movements/move.html",
            {"user": user, "item": item, "error": str(exc), **form_choices(db)},
            status_code=400,
        )

    db.commit()
    return redirect(f"/items/{item.id}", flash="Перемещение записано в журнал.")


@router.get("/items/{item_id}/issue", response_class=HTMLResponse)
def issue_form(item_id: int, request: Request, db: DbSession, user: EditorUser):
    item = _require_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "movements/issue.html",
        {"user": user, "item": item, **form_choices(db)},
    )


@router.post("/items/{item_id}/issue")
async def issue(item_id: int, request: Request, db: DbSession, user: EditorUser):
    item = _require_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    try:
        target = location_from_form(db, form)
        movements_service.issue_item(
            db,
            item=item,
            employee_id=target.employee_id,
            room_id=target.room_id,
            actor=user,
            expected_return_date=_parse_date(form.get("expected_return_date")),
            comment=form.get("comment"),
        )
    except ServiceError as exc:
        db.rollback()
        return render(
            request,
            "movements/issue.html",
            {"user": user, "item": item, "error": str(exc), **form_choices(db)},
            status_code=400,
        )

    db.commit()
    return redirect(f"/items/{item.id}", flash="Выдача записана.")


@router.get("/items/{item_id}/return", response_class=HTMLResponse)
def return_form(item_id: int, request: Request, db: DbSession, user: EditorUser):
    item = _require_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "movements/return.html",
        {"user": user, "item": item, **form_choices(db)},
    )


@router.post("/items/{item_id}/return")
async def return_item(item_id: int, request: Request, db: DbSession, user: EditorUser):
    item = _require_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    try:
        movements_service.return_to_storage(
            db,
            item=item,
            storage_place_id=int_or_none(form.get("storage_place_id")),
            actor=user,
            comment=form.get("comment"),
        )
    except ServiceError as exc:
        db.rollback()
        return render(
            request,
            "movements/return.html",
            {"user": user, "item": item, "error": str(exc), **form_choices(db)},
            status_code=400,
        )

    db.commit()
    return redirect(f"/items/{item.id}", flash="Возврат записан.")


@router.get("/items/{item_id}/write-off", response_class=HTMLResponse)
def write_off_form(item_id: int, request: Request, db: DbSession, user: EditorUser):
    item = _require_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "movements/write_off.html",
        {"user": user, "item": item, "contents": tree.contents(db, item)},
    )


@router.post("/items/{item_id}/write-off")
async def write_off(item_id: int, request: Request, db: DbSession, user: EditorUser):
    item = _require_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    try:
        movements_service.write_off_item(
            db, item=item, actor=user, comment=form.get("comment")
        )
    except ServiceError as exc:
        db.rollback()
        return render(
            request,
            "movements/write_off.html",
            {
                "user": user,
                "item": item,
                "contents": tree.contents(db, item),
                "error": str(exc),
            },
            status_code=400,
        )

    db.commit()
    return redirect(f"/items/{item.id}", flash=f"Единица {item.inv_number} списана.")


@router.get("/movements", response_class=HTMLResponse)
def all_movements(request: Request, db: DbSession, user: ViewerUser):
    recent = list(
        db.scalars(
            select(Movement).order_by(Movement.moved_at.desc(), Movement.id.desc()).limit(200)
        )
    )
    return render(request, "movements/list.html", {"user": user, "movements": recent})


# --- internals ---------------------------------------------------------------


def _require_item(db: DbSession, item_id: int) -> Optional[Item]:
    return items_service.get_item(db, item_id)


def _parse_date(value: Optional[str]) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ServiceError("Некорректная дата возврата.") from exc
