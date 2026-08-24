"""Accounts, from the interface. Admin only — it is the one screen that hands out
access, and everything it does is visible on the same page."""


from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth.deps import AdminUser, AnyUser, DbSession
from app.models.enums import UserRole
from app.routers.helpers import int_or_none
from app.services import users as users_service
from app.services.errors import ServiceError
from app.templating import redirect, render

router = APIRouter()


@router.get("/admin/users", response_class=HTMLResponse)
def user_list(request: Request, db: DbSession, user: AdminUser) -> HTMLResponse:
    return render(
        request,
        "admin/users.html",
        {
            "user": user,
            "users": users_service.all_users(db),
            "employees": users_service.unlinked_employees(db),
            "roles": list(UserRole),
        },
    )


@router.post("/admin/users/new")
async def create_user(request: Request, db: DbSession, user: AdminUser):
    form = await request.form()
    try:
        created = users_service.create_user(
            db,
            username=form.get("username") or "",
            password=form.get("password") or "",
            role=_role_or_default(form.get("role")),
            full_name=form.get("full_name") or "",
            employee_id=int_or_none(form.get("employee_id")),
        )
    except ServiceError as exc:
        db.rollback()
        return redirect("/admin/users", flash=str(exc), kind="warn")
    db.commit()
    return redirect("/admin/users", flash=f"Учётная запись «{created.username}» создана.")


@router.get("/admin/users/{user_id}", response_class=HTMLResponse)
def edit_user(user_id: int, request: Request, db: DbSession, user: AdminUser):
    target = users_service.get_user(db, user_id)
    if target is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "admin/user_form.html",
        {
            "user": user,
            "target": target,
            "employees": users_service.unlinked_employees(db, keep=target.employee_id),
            "roles": list(UserRole),
        },
    )


@router.post("/admin/users/{user_id}")
async def update_user(user_id: int, request: Request, db: DbSession, user: AdminUser):
    target = users_service.get_user(db, user_id)
    if target is None:
        return redirect("/admin/users", flash="Учётная запись не найдена.", kind="warn")

    form = await request.form()
    try:
        users_service.update_user(
            db,
            user=target,
            role=_role_or_default(form.get("role")),
            full_name=form.get("full_name") or "",
            employee_id=int_or_none(form.get("employee_id")),
            is_active=form.get("is_active") is not None,
            actor=user,
        )
    except ServiceError as exc:
        db.rollback()
        return redirect(f"/admin/users/{user_id}", flash=str(exc), kind="warn")
    db.commit()
    return redirect("/admin/users", flash="Изменения сохранены.")


@router.post("/admin/users/{user_id}/password")
async def reset_password(user_id: int, request: Request, db: DbSession, user: AdminUser):
    target = users_service.get_user(db, user_id)
    if target is None:
        return redirect("/admin/users", flash="Учётная запись не найдена.", kind="warn")

    form = await request.form()
    try:
        users_service.set_password(db, user=target, password=form.get("password") or "")
    except ServiceError as exc:
        db.rollback()
        return redirect(f"/admin/users/{user_id}", flash=str(exc), kind="warn")
    db.commit()
    return redirect(
        f"/admin/users/{user_id}",
        flash=f"Пароль для «{target.username}» изменён. Передайте его лично.",
    )


@router.get("/profile", response_class=HTMLResponse)
def profile(request: Request, db: DbSession, user: AnyUser) -> HTMLResponse:
    """Every account, whatever the role: who I am and how to change my password."""
    return render(request, "profile.html", {"user": user})


@router.post("/profile/password")
async def change_password(request: Request, db: DbSession, user: AnyUser):
    form = await request.form()
    try:
        users_service.change_own_password(
            db,
            user=user,
            current=form.get("current_password") or "",
            new=form.get("new_password") or "",
        )
    except ServiceError as exc:
        db.rollback()
        return redirect("/profile", flash=str(exc), kind="warn")
    db.commit()
    return redirect("/profile", flash="Пароль изменён.")


def _role_or_default(raw) -> UserRole:
    try:
        return UserRole(raw)
    except (ValueError, TypeError):
        return UserRole.EMPLOYEE
