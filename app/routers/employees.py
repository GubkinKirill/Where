from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.auth.deps import DbSession, EditorUser, ViewerUser
from app.models.directory import Employee
from app.routers.helpers import int_or_none
from app.services import consumables as consumables_service
from app.services import employees as employees_service
from app.services import movements as movements_service
from app.services import requests as requests_service
from app.services import users as users_service
from app.services.errors import ServiceError
from app.templating import redirect, render

router = APIRouter()


@router.get("/employees/{employee_id}", response_class=HTMLResponse)
def employee_card(employee_id: int, request: Request, db: DbSession, user: ViewerUser):
    employee = employees_service.get_employee(db, employee_id)
    if employee is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    held = employees_service.items_of(db, employee)
    return render(
        request,
        "employees/card.html",
        {
            "user": user,
            "employee": employee,
            "items": held,
            "open_issues": {
                item.id: movements_service.open_issue(db, item) for item in held
            },
            "account": users_service.account_of(db, employee),
            "consumables": consumables_service.issued_to(db, employee, limit=10),
            "requests": requests_service.of_employee(db, employee)[:5],
            "colleagues": list(
                db.scalars(
                    select(Employee)
                    .where(Employee.is_active, Employee.id != employee.id)
                    .order_by(Employee.full_name)
                )
            ),
        },
    )


@router.post("/employees/{employee_id}/transfer")
async def transfer(employee_id: int, request: Request, db: DbSession, user: EditorUser):
    employee = employees_service.get_employee(db, employee_id)
    if employee is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)

    form = await request.form()
    target = employees_service.get_employee(db, int_or_none(form.get("target_id")) or 0)
    if target is None:
        return redirect(
            f"/employees/{employee_id}", flash="Сотрудник не выбран.", kind="warn"
        )

    try:
        moved = employees_service.transfer_items(
            db, source=employee, target=target, actor=user, comment=form.get("comment")
        )
    except ServiceError as exc:
        db.rollback()
        return redirect(f"/employees/{employee_id}", flash=str(exc), kind="warn")

    db.commit()
    if not moved:
        return redirect(f"/employees/{employee_id}", flash="Передавать нечего.", kind="warn")
    return redirect(
        f"/employees/{target.id}",
        flash=f"Передано единиц: {len(moved)}. Каждая записана в журнал.",
    )


@router.post("/employees/{employee_id}/dismiss")
def dismiss(employee_id: int, db: DbSession, user: EditorUser):
    employee = employees_service.get_employee(db, employee_id)
    if employee is None:
        return redirect("/directories/employees", flash="Сотрудник не найден.", kind="warn")

    employees_service.set_active(db, employee=employee, is_active=False)
    held = len(employees_service.items_of(db, employee))
    db.commit()

    if held:
        return redirect(
            f"/employees/{employee_id}",
            flash=f"Сотрудник отмечен уволенным. За ним ещё числится единиц: {held}.",
            kind="warn",
        )
    return redirect(f"/employees/{employee_id}", flash="Сотрудник отмечен уволенным.")


@router.post("/employees/{employee_id}/restore")
def restore(employee_id: int, db: DbSession, user: EditorUser):
    employee = employees_service.get_employee(db, employee_id)
    if employee is None:
        return redirect("/directories/employees", flash="Сотрудник не найден.", kind="warn")

    employees_service.set_active(db, employee=employee, is_active=True)
    db.commit()
    return redirect(f"/employees/{employee_id}", flash="Сотрудник снова числится работающим.")
