from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.deps import AdminUser, DbSession, ViewerUser
from app.models.item import ItemType
from app.models.kit import KitTemplate, KitTemplateLine
from app.routers.helpers import int_or_none
from app.services import kits as kits_service
from app.templating import redirect, render

router = APIRouter()

# blank rows offered on the template form, so lines can be added without extra clicks
BLANK_LINES = 3


@router.get("/kits", response_class=HTMLResponse)
def kit_report(request: Request, db: DbSession, user: ViewerUser) -> HTMLResponse:
    return render(
        request,
        "kits/report.html",
        {"user": user, "kits": kits_service.all_kits(db)},
    )


@router.get("/kits/templates", response_class=HTMLResponse)
def template_list(request: Request, db: DbSession, user: ViewerUser) -> HTMLResponse:
    return render(
        request,
        "kits/templates.html",
        {"user": user, "templates": kits_service.templates(db)},
    )


@router.get("/kits/templates/new", response_class=HTMLResponse)
def new_template_form(request: Request, db: DbSession, user: AdminUser) -> HTMLResponse:
    return render(
        request,
        "kits/template_form.html",
        {"user": user, "template": None, "types": _types(db), "blank_lines": BLANK_LINES},
    )


@router.post("/kits/templates/new")
async def create_template(request: Request, db: DbSession, user: AdminUser):
    form = await request.form()
    template = KitTemplate(name=(form.get("name") or "").strip())
    if not template.name:
        return redirect("/kits/templates/new", flash="Укажите название.", kind="warn")

    _apply_template(template, form)
    db.add(template)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return redirect(
            "/kits/templates/new",
            flash="Шаблон с таким названием уже есть, либо тип указан дважды.",
            kind="warn",
        )
    return redirect("/kits/templates", flash="Шаблон комплектности создан.")


@router.get("/kits/templates/{template_id}", response_class=HTMLResponse)
def edit_template_form(
    template_id: int, request: Request, db: DbSession, user: AdminUser
) -> HTMLResponse:
    template = db.get(KitTemplate, template_id)
    if template is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "kits/template_form.html",
        {"user": user, "template": template, "types": _types(db), "blank_lines": BLANK_LINES},
    )


@router.post("/kits/templates/{template_id}")
async def update_template(
    template_id: int, request: Request, db: DbSession, user: AdminUser
):
    template = db.get(KitTemplate, template_id)
    if template is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        return redirect(f"/kits/templates/{template_id}", flash="Укажите название.", kind="warn")
    template.name = name

    _apply_template(template, form)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return redirect(
            f"/kits/templates/{template_id}",
            flash="Название занято, либо один тип указан дважды.",
            kind="warn",
        )
    return redirect("/kits/templates", flash="Шаблон сохранён.")


@router.post("/kits/templates/{template_id}/delete")
def delete_template(template_id: int, db: DbSession, user: AdminUser):
    template = db.get(KitTemplate, template_id)
    if template is None:
        return redirect("/kits/templates", flash="Шаблон не найден.", kind="warn")
    db.delete(template)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return redirect(
            "/kits/templates",
            flash="Шаблон назначен комплектам и не может быть удалён.",
            kind="warn",
        )
    return redirect("/kits/templates", flash="Шаблон удалён.")


# --- internals ---------------------------------------------------------------


def _types(db: DbSession) -> list[ItemType]:
    return list(db.scalars(select(ItemType).order_by(ItemType.sort_order, ItemType.name)))


def _apply_template(template: KitTemplate, form) -> None:
    template.description = (form.get("description") or "").strip() or None
    template.is_active = form.get("is_active") is not None

    type_ids = form.getlist("line_type_id")
    quantities = form.getlist("line_quantity")
    notes = form.getlist("line_note")

    template.lines.clear()
    for index, raw_type_id in enumerate(type_ids):
        type_id = int_or_none(raw_type_id)
        if type_id is None:
            continue
        quantity = int_or_none(quantities[index] if index < len(quantities) else None) or 1
        note = (notes[index] if index < len(notes) else "") or ""
        template.lines.append(
            KitTemplateLine(
                item_type_id=type_id,
                quantity=max(1, quantity),
                note=note.strip() or None,
            )
        )
