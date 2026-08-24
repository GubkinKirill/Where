"""Consumables: a list, a card with its ledger, and the three operations —
receipt, issue, correction after a recount. Nothing here writes a quantity
directly; every button goes through services.consumables.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy import select

from app.auth.deps import AdminUser, DbSession, EditorUser, ViewerUser
from app.models.directory import Employee, StoragePlace
from app.routers.helpers import int_or_none
from app.schemas.consumable import ConsumableFilter, ConsumableForm
from app.services import consumables as consumables_service
from app.services.errors import ServiceError
from app.templating import redirect, render

router = APIRouter()


@router.get("/consumables", response_class=HTMLResponse)
def stock_list(request: Request, db: DbSession, user: ViewerUser) -> HTMLResponse:
    filters = ConsumableFilter(**dict(request.query_params))
    found = consumables_service.search(db, filters)
    return render(
        request,
        "consumables/list.html",
        {
            "user": user,
            "stocks": found,
            "filters": filters,
            "low_count": consumables_service.low_stock_count(db),
            **_choices(db),
        },
    )


@router.get("/consumables/new", response_class=HTMLResponse)
def new_stock_form(request: Request, db: DbSession, user: EditorUser) -> HTMLResponse:
    return render(
        request,
        "consumables/form.html",
        {"user": user, "stock": None, "values": {}, **_choices(db)},
    )


@router.post("/consumables/new")
async def create_stock(request: Request, db: DbSession, user: EditorUser):
    form = await request.form()
    try:
        stock = consumables_service.create_stock(
            db,
            form=ConsumableForm(**_form_dict(form)),
            quantity=int_or_none(form.get("quantity")) or 0,
            actor=user,
            comment=(form.get("comment") or "").strip() or None,
        )
    except (ValidationError, ServiceError) as exc:
        db.rollback()
        return _form_error(request, db, user, form, exc, stock=None)
    db.commit()
    return redirect(f"/consumables/{stock.id}", flash=f"Позиция «{stock.name}» заведена.")


@router.get("/consumables/{stock_id}", response_class=HTMLResponse)
def stock_card(stock_id: int, request: Request, db: DbSession, user: ViewerUser):
    stock = consumables_service.get_stock(db, stock_id)
    if stock is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "consumables/card.html",
        {
            "user": user,
            "stock": stock,
            "history": consumables_service.history(db, stock),
            **_choices(db),
        },
    )


@router.get("/consumables/{stock_id}/edit", response_class=HTMLResponse)
def edit_stock_form(stock_id: int, request: Request, db: DbSession, user: EditorUser):
    stock = consumables_service.get_stock(db, stock_id)
    if stock is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "consumables/form.html",
        {"user": user, "stock": stock, "values": _values(stock), **_choices(db)},
    )


@router.post("/consumables/{stock_id}/edit")
async def update_stock(stock_id: int, request: Request, db: DbSession, user: EditorUser):
    stock = consumables_service.get_stock(db, stock_id)
    if stock is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    try:
        consumables_service.update_stock(
            db, stock=stock, form=ConsumableForm(**_form_dict(form))
        )
    except (ValidationError, ServiceError) as exc:
        db.rollback()
        return _form_error(request, db, user, form, exc, stock=stock)
    db.commit()
    return redirect(f"/consumables/{stock.id}", flash="Изменения сохранены.")


@router.post("/consumables/{stock_id}/receive")
async def receive(stock_id: int, request: Request, db: DbSession, user: EditorUser):
    return await _operation(stock_id, request, db, user, "receive")


@router.post("/consumables/{stock_id}/issue")
async def issue(stock_id: int, request: Request, db: DbSession, user: EditorUser):
    return await _operation(stock_id, request, db, user, "issue")


@router.post("/consumables/{stock_id}/adjust")
async def adjust(stock_id: int, request: Request, db: DbSession, user: EditorUser):
    return await _operation(stock_id, request, db, user, "adjust")


@router.post("/consumables/{stock_id}/delete")
def delete_stock(stock_id: int, db: DbSession, user: AdminUser):
    stock = consumables_service.get_stock(db, stock_id)
    if stock is None:
        return redirect("/consumables", flash="Позиция не найдена.", kind="warn")
    try:
        consumables_service.delete_stock(db, stock=stock)
    except ServiceError as exc:
        db.rollback()
        return redirect(f"/consumables/{stock_id}", flash=str(exc), kind="warn")
    db.commit()
    return redirect("/consumables", flash="Позиция удалена.")


# --- internals ---------------------------------------------------------------


async def _operation(stock_id: int, request: Request, db: DbSession, user, kind: str):
    stock = consumables_service.get_stock(db, stock_id)
    if stock is None:
        return redirect("/consumables", flash="Позиция не найдена.", kind="warn")

    form = await request.form()
    amount = int_or_none(form.get("quantity"))
    comment = (form.get("comment") or "").strip() or None
    if amount is None:
        return redirect(f"/consumables/{stock_id}", flash="Укажите количество.", kind="warn")

    try:
        if kind == "receive":
            consumables_service.receive(
                db, stock=stock, quantity=amount, actor=user, comment=comment
            )
            message = f"Приход: {amount} {stock.unit}"
        elif kind == "issue":
            consumables_service.issue(
                db,
                stock=stock,
                quantity=amount,
                employee_id=int_or_none(form.get("employee_id")),
                actor=user,
                comment=comment,
            )
            message = f"Расход: {amount} {stock.unit}"
        else:
            consumables_service.adjust(
                db, stock=stock, counted=amount, actor=user, comment=comment
            )
            message = f"Остаток исправлен: {amount} {stock.unit}"
    except ServiceError as exc:
        db.rollback()
        return redirect(f"/consumables/{stock_id}", flash=str(exc), kind="warn")

    db.commit()
    return redirect(f"/consumables/{stock_id}", flash=message)


def _choices(db: DbSession) -> dict:
    return {
        "categories": consumables_service.categories(db),
        "storage_places": list(db.scalars(select(StoragePlace).order_by(StoragePlace.code))),
        "employees": list(
            db.scalars(select(Employee).where(Employee.is_active).order_by(Employee.full_name))
        ),
    }


def _form_dict(form) -> dict:
    fields = ("name", "category", "unit", "min_quantity", "storage_place_id", "notes")
    values = {name: form.get(name) for name in fields}
    values["is_active"] = form.get("is_active") is not None
    return values


def _values(stock) -> dict:
    return {
        "name": stock.name,
        "category": stock.category,
        "unit": stock.unit,
        "min_quantity": stock.min_quantity,
        "storage_place_id": stock.storage_place_id,
        "notes": stock.notes or "",
        "is_active": stock.is_active,
    }


def _form_error(request: Request, db: DbSession, user, form, exc, stock):
    message = (
        "Проверьте поля формы." if isinstance(exc, ValidationError) else str(exc)
    )
    return render(
        request,
        "consumables/form.html",
        {
            "user": user,
            "stock": stock,
            "values": dict(form),
            "error": message,
            **_choices(db),
        },
        status_code=400,
    )
