from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.auth.deps import AdminUser, DbSession, EditorUser, ViewerUser
from app.models.item import Item
from app.schemas.item import ItemFilter, ItemForm
from app.services import items as items_service
from app.services import kits as kits_service
from app.services import movements as movements_service
from app.services import tree
from app.services.errors import ServiceError
from app.routers.helpers import attributes_from_form, form_choices, location_from_form
from app.templating import redirect, render

router = APIRouter()


@router.get("/items", response_class=HTMLResponse)
def item_list(request: Request, db: DbSession, user: ViewerUser) -> HTMLResponse:
    # a stale bookmark or a hand-typed value must not take the whole list down
    try:
        filters = ItemFilter(**dict(request.query_params))
        bad_filter = None
    except ValidationError:
        filters = ItemFilter()
        bad_filter = "Фильтр не понят, показан весь список."
    found = items_service.search_items(db, filters)
    context = {
        "user": user,
        "items": found,
        "filters": filters,
        "total": items_service.count_items(db),
        "open_issues": movements_service.open_issues_for(db, found),
        "error": bad_filter,
        **form_choices(db),
    }
    if request.headers.get("HX-Request"):
        return render(request, "items/_rows.html", context)
    return render(request, "items/list.html", context)


@router.get("/find")
def find(request: Request, db: DbSession, user: ViewerUser):
    """Сквозной поиск из шапки. В руках наклейка с номером — и этого достаточно:
    точное совпадение или единственная находка открывают карточку сразу, всё
    остальное показывается списком с тем же запросом."""
    query = (request.query_params.get("q") or "").strip()
    if not query:
        return redirect("/items")

    exact = items_service.get_by_inv_number(db, query)
    if exact is not None:
        return redirect(f"/items/{exact.id}")

    found = items_service.search_items(db, ItemFilter(q=query, limit=2))
    if len(found) == 1:
        return redirect(f"/items/{found[0].id}")
    return redirect(f"/items?q={quote(query)}")


@router.get("/items/new", response_class=HTMLResponse)
def new_item_form(request: Request, db: DbSession, user: EditorUser) -> HTMLResponse:
    return render(
        request,
        "items/form.html",
        {"user": user, "item": None, "values": {}, "attributes": {}, **form_choices(db)},
    )


@router.post("/items/new")
async def create_item(request: Request, db: DbSession, user: EditorUser):
    form = await request.form()
    try:
        item_form = ItemForm(**_form_dict(form))
        location = location_from_form(db, form)
        item = items_service.create_item(
            db,
            form=item_form,
            location=location,
            actor=user,
            attributes=attributes_from_form(form),
            comment=(form.get("comment") or "").strip() or None,
        )
    except (ValidationError, ServiceError) as exc:
        db.rollback()
        return _form_with_error(request, db, user, form, exc, item=None)

    duplicates = items_service.legacy_number_duplicates(
        db, item.legacy_number, exclude_id=item.id
    )
    db.commit()
    message = f"Единица {item.inv_number} добавлена."
    if duplicates:
        others = ", ".join(other.inv_number for other in duplicates)
        return redirect(
            f"/items/{item.id}",
            flash=f"{message} Прежний номер {item.legacy_number} уже есть у: {others}.",
            kind="warn",
        )
    return redirect(f"/items/{item.id}", flash=message)


@router.get("/items/{item_id}", response_class=HTMLResponse)
def item_card(
    item_id: int, request: Request, db: DbSession, user: ViewerUser
) -> HTMLResponse:
    item = items_service.get_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "items/card.html",
        {
            "user": user,
            "item": item,
            "contents": tree.contents(db, item),
            "ancestors": tree.ancestors(db, item),
            "outermost": tree.outermost(db, item),
            "kit": kits_service.status(db, item),
            "history": movements_service.history(db, item),
            "open_issue": movements_service.open_issue(db, item),
            "duplicates": items_service.legacy_number_duplicates(
                db, item.legacy_number, exclude_id=item.id
            ),
        },
    )


@router.get("/items/{item_id}/edit", response_class=HTMLResponse)
def edit_item_form(
    item_id: int, request: Request, db: DbSession, user: EditorUser
) -> HTMLResponse:
    item = items_service.get_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "items/form.html",
        {
            "user": user,
            "item": item,
            "values": _values_from_item(item),
            "attributes": {a.key: a.value for a in item.attributes},
            **form_choices(db),
        },
    )


@router.post("/items/{item_id}/edit")
async def edit_item(item_id: int, request: Request, db: DbSession, user: EditorUser):
    item = items_service.get_item(db, item_id)
    if item is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    try:
        item_form = ItemForm(**_form_dict(form))
        items_service.update_item(
            db, item=item, form=item_form, attributes=attributes_from_form(form)
        )
    except (ValidationError, ServiceError) as exc:
        db.rollback()
        return _form_with_error(request, db, user, form, exc, item=item)

    db.commit()
    return redirect(f"/items/{item.id}", flash="Изменения сохранены.")


@router.post("/items/{item_id}/delete")
def delete_item(item_id: int, db: DbSession, user: AdminUser):
    item = items_service.get_item(db, item_id)
    if item is None:
        return redirect("/items", flash="Единица не найдена.", kind="warn")
    if tree.contents(db, item):
        return redirect(
            f"/items/{item_id}",
            flash="Сначала выньте вложенные единицы.",
            kind="warn",
        )
    inv_number = item.inv_number
    db.delete(item)
    db.commit()
    return redirect("/items", flash=f"Единица {inv_number} удалена без следа в журнале.")


# --- internals ---------------------------------------------------------------


def _form_dict(form) -> dict[str, Any]:
    fields = (
        "type_id",
        "name",
        "legacy_number",
        "manufacturer",
        "model",
        "serial_number",
        "status",
        "condition_note",
        "purchase_date",
        "warranty_until",
        "notes",
        "kit_template_id",
        "project_id",
    )
    return {name: form.get(name) for name in fields if form.get(name) is not None}


def _values_from_item(item: Item) -> dict[str, Any]:
    return {
        "type_id": item.type_id,
        "name": item.name,
        "legacy_number": item.legacy_number or "",
        "manufacturer": item.manufacturer or "",
        "model": item.model or "",
        "serial_number": item.serial_number or "",
        "status": item.status.value,
        "condition_note": item.condition_note or "",
        "purchase_date": item.purchase_date.isoformat() if item.purchase_date else "",
        "warranty_until": item.warranty_until.isoformat() if item.warranty_until else "",
        "notes": item.notes or "",
        "kit_template_id": item.kit_template_id or "",
        "project_id": item.project_id or "",
    }


def _error_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        missing = ", ".join(str(error["loc"][0]) for error in exc.errors())
        return f"Проверьте заполнение полей: {missing}."
    return str(exc)


def _form_with_error(
    request: Request, db: DbSession, user, form, exc: Exception, item: Optional[Item]
) -> HTMLResponse:
    return render(
        request,
        "items/form.html",
        {
            "user": user,
            "item": item,
            "values": dict(form),
            "attributes": attributes_from_form(form),
            "error": _error_text(exc),
            **form_choices(db),
        },
        status_code=400,
    )
