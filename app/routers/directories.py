"""CRUD for the five reference books. They differ only by their field lists,
so the shape of each one is declared here and rendered by two shared templates."""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import AdminUser, DbSession, ViewerUser
from app.i18n import STORAGE_KIND_LABELS
from app.models.base import Base
from app.models.directory import Department, Employee, Room, StoragePlace
from app.models.enums import StoragePlaceKind
from app.models.item import ItemType
from app.routers.helpers import int_or_none
from app.templating import redirect, render

router = APIRouter()


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"  # text | number | checkbox | select | textarea | list
    required: bool = False
    options: Optional[str] = None
    hint: str = ""


@dataclass(frozen=True)
class Directory:
    slug: str
    title: str
    one: str
    model: type[Base]
    fields: tuple[Field, ...]
    columns: tuple[tuple[str, str], ...]
    order: Callable[[], Any]


DIRECTORIES: dict[str, Directory] = {
    "types": Directory(
        slug="types",
        title="Типы единиц",
        one="тип единицы",
        model=ItemType,
        fields=(
            Field("code", "Код (префикс номера)", required=True, hint="PC, MON, RAM, RPI…"),
            Field("name", "Название", required=True),
            Field("is_container", "Может содержать вложенные единицы", kind="checkbox"),
            Field("icon", "Значок", hint="один символ или эмодзи"),
            Field(
                "suggested_attributes",
                "Подсказываемые атрибуты",
                kind="list",
                hint="по одному в строке: назначение, образ ОС, MAC, IP",
            ),
            Field("sort_order", "Порядок в списках", kind="number"),
            Field("is_active", "Используется", kind="checkbox"),
        ),
        columns=(
            ("code", "Код"),
            ("name", "Название"),
            ("is_container", "Контейнер"),
            ("sort_order", "Порядок"),
            ("is_active", "Используется"),
        ),
        order=lambda: (ItemType.sort_order, ItemType.code),
    ),
    "employees": Directory(
        slug="employees",
        title="Сотрудники",
        one="сотрудника",
        model=Employee,
        fields=(
            Field("full_name", "ФИО", required=True),
            Field("position", "Должность"),
            Field("department_id", "Отдел", kind="select", options="departments"),
            Field("default_room_id", "Кабинет по умолчанию", kind="select", options="rooms"),
            Field("is_active", "Работает", kind="checkbox"),
        ),
        columns=(
            ("full_name", "ФИО"),
            ("position", "Должность"),
            ("department", "Отдел"),
            ("default_room", "Кабинет"),
            ("is_active", "Работает"),
        ),
        order=lambda: (Employee.full_name,),
    ),
    "departments": Directory(
        slug="departments",
        title="Отделы",
        one="отдел",
        model=Department,
        fields=(
            Field("code", "Код", required=True, hint="например, 235"),
            Field("name", "Название", required=True),
        ),
        columns=(("code", "Код"), ("name", "Название")),
        order=lambda: (Department.code,),
    ),
    "rooms": Directory(
        slug="rooms",
        title="Кабинеты",
        one="кабинет",
        model=Room,
        fields=(
            Field("number", "Номер", required=True),
            Field("floor", "Этаж", kind="number"),
            Field("description", "Описание"),
        ),
        columns=(("number", "Номер"), ("floor", "Этаж"), ("description", "Описание")),
        order=lambda: (Room.number,),
    ),
    "storage": Directory(
        slug="storage",
        title="Места хранения",
        one="место хранения",
        model=StoragePlace,
        fields=(
            Field("code", "Код", required=True, hint="для QR: SHELF-02"),
            Field("name", "Название", required=True),
            Field("kind", "Вид", kind="select", options="storage_kinds", required=True),
            Field("parent_id", "Входит в", kind="select", options="storage_places"),
            Field("notes", "Заметки", kind="textarea"),
        ),
        columns=(
            ("code", "Код"),
            ("full_path", "Путь"),
            ("kind", "Вид"),
        ),
        order=lambda: (StoragePlace.code,),
    ),
}


@router.get("/directories", response_class=HTMLResponse)
def directory_index(request: Request, user: ViewerUser) -> HTMLResponse:
    return render(
        request,
        "directories/index.html",
        {"user": user, "directories": list(DIRECTORIES.values())},
    )


@router.get("/directories/{slug}", response_class=HTMLResponse)
def directory_list(slug: str, request: Request, db: DbSession, user: ViewerUser):
    spec = DIRECTORIES.get(slug)
    if spec is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    records = list(db.scalars(select(spec.model).order_by(*spec.order())))
    rows = [
        {"id": record.id, "cells": [_cell(record, name) for name, _ in spec.columns]}
        for record in records
    ]
    return render(
        request,
        "directories/list.html",
        {"user": user, "spec": spec, "rows": rows},
    )


@router.get("/directories/{slug}/new", response_class=HTMLResponse)
def new_record_form(slug: str, request: Request, db: DbSession, user: AdminUser):
    spec = DIRECTORIES.get(slug)
    if spec is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "directories/form.html",
        {"user": user, "spec": spec, "record": None, "values": {}, "options": _options(db)},
    )


@router.post("/directories/{slug}/new")
async def create_record(slug: str, request: Request, db: DbSession, user: AdminUser):
    spec = DIRECTORIES.get(slug)
    if spec is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    form = await request.form()
    record = spec.model()
    _apply(record, spec, form)
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _form_error(request, db, user, spec, None, form)
    return redirect(f"/directories/{slug}", flash="Запись добавлена.")


@router.get("/directories/{slug}/{record_id}", response_class=HTMLResponse)
def edit_record_form(
    slug: str, record_id: int, request: Request, db: DbSession, user: AdminUser
):
    spec = DIRECTORIES.get(slug)
    if spec is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    record = db.get(spec.model, record_id)
    if record is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "directories/form.html",
        {
            "user": user,
            "spec": spec,
            "record": record,
            "values": _values(record, spec),
            "options": _options(db),
        },
    )


@router.post("/directories/{slug}/{record_id}")
async def update_record(
    slug: str, record_id: int, request: Request, db: DbSession, user: AdminUser
):
    spec = DIRECTORIES.get(slug)
    if spec is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    record = db.get(spec.model, record_id)
    if record is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    form = await request.form()
    _apply(record, spec, form)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _form_error(request, db, user, spec, record, form)
    return redirect(f"/directories/{slug}", flash="Изменения сохранены.")


@router.post("/directories/{slug}/{record_id}/delete")
def delete_record(slug: str, record_id: int, db: DbSession, user: AdminUser):
    spec = DIRECTORIES.get(slug)
    if spec is None:
        return redirect("/directories", flash="Справочник не найден.", kind="warn")
    record = db.get(spec.model, record_id)
    if record is None:
        return redirect(f"/directories/{slug}", flash="Запись не найдена.", kind="warn")
    db.delete(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return redirect(
            f"/directories/{slug}",
            flash="Запись используется и не может быть удалена.",
            kind="warn",
        )
    return redirect(f"/directories/{slug}", flash="Запись удалена.")


# --- internals ---------------------------------------------------------------


def _options(db: Session) -> dict[str, list[tuple[Any, str]]]:
    return {
        "departments": [(d.id, str(d)) for d in db.scalars(select(Department).order_by(Department.code))],
        "rooms": [(r.id, r.number) for r in db.scalars(select(Room).order_by(Room.number))],
        "storage_places": [
            (p.id, p.full_path) for p in db.scalars(select(StoragePlace).order_by(StoragePlace.code))
        ],
        "storage_kinds": [(kind.value, STORAGE_KIND_LABELS[kind]) for kind in StoragePlaceKind],
    }


def _cell(record: Any, name: str) -> str:
    value = getattr(record, name, None)
    if isinstance(value, bool):
        return "да" if value else "нет"
    if value is None or value == "":
        return "—"
    if isinstance(value, StoragePlaceKind):
        return STORAGE_KIND_LABELS[value]
    return str(value)


def _values(record: Any, spec: Directory) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in spec.fields:
        value = getattr(record, field.name, None)
        if field.kind == "list":
            values[field.name] = "\n".join(value or [])
        elif hasattr(value, "value"):  # enum
            values[field.name] = value.value
        else:
            values[field.name] = "" if value is None else value
    return values


def _apply(record: Any, spec: Directory, form) -> None:
    for field in spec.fields:
        raw = form.get(field.name)
        if field.kind == "checkbox":
            setattr(record, field.name, raw is not None)
        elif field.kind == "number":
            setattr(record, field.name, int_or_none(raw))
        elif field.kind == "list":
            lines = [line.strip() for line in (raw or "").splitlines() if line.strip()]
            setattr(record, field.name, lines)
        elif field.kind == "select" and field.options != "storage_kinds":
            setattr(record, field.name, int_or_none(raw))
        else:
            value = (raw or "").strip()
            setattr(record, field.name, value or None if not field.required else value)


def _form_error(request: Request, db: Session, user, spec: Directory, record, form):
    return render(
        request,
        "directories/form.html",
        {
            "user": user,
            "spec": spec,
            "record": record,
            "values": dict(form),
            "options": _options(db),
            "error": "Значение уже занято или нарушает связи справочника.",
        },
        status_code=400,
    )
