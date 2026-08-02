"""Self service for people without an account: «what is assigned to me».

Opens without a login — the employee identifies themselves with the number printed
on their pass. That is identification, not authentication: anyone who knows the
number sees the list, so this page shows only equipment, nothing else about the
person, and it never puts the number into a URL.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.auth.deps import DbSession
from app.models.directory import Employee
from app.services import employees as employees_service
from app.services import movements as movements_service
from app.services import tree
from app.templating import render

router = APIRouter()


@router.get("/my", response_class=HTMLResponse)
def enter_number(request: Request) -> HTMLResponse:
    return render(request, "self/enter.html", {})


@router.post("/my", response_class=HTMLResponse)
async def show_my_items(request: Request, db: DbSession) -> HTMLResponse:
    form = await request.form()
    number = (form.get("personnel_number") or "").strip()

    employee = None
    if number:
        employee = db.scalars(
            select(Employee).where(Employee.personnel_number == number)
        ).first()

    if employee is None:
        return render(
            request,
            "self/enter.html",
            {"error": "Сотрудник с таким табельным номером не найден."},
            status_code=404,
        )

    held = employees_service.items_of(db, employee)
    return render(
        request,
        "self/items.html",
        {
            "employee": employee,
            "items": held,
            "contents": {item.id: tree.contents(db, item) for item in held},
            "open_issues": {
                item.id: movements_service.open_issue(db, item) for item in held
            },
        },
    )
