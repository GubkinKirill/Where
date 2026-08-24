from typing import Annotated, Optional

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.session import read_user_id
from app.db import get_db
from app.models.enums import UserRole
from app.models.user import User


class AuthRequired(Exception):
    """Not signed in — the handler redirects to the login page."""


class AccessDenied(Exception):
    def __init__(self, required: UserRole) -> None:
        self.required = required


def get_current_user(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> Optional[User]:
    user_id = read_user_id(request)
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


CurrentUser = Annotated[Optional[User], Depends(get_current_user)]


def require_user(user: CurrentUser) -> User:
    if user is None:
        raise AuthRequired()
    return user


def require_role(role: UserRole):
    def dependency(user: Annotated[User, Depends(require_user)]) -> User:
        if not user.can(role):
            raise AccessDenied(role)
        return user

    return dependency


class NoEmployeeLinked(Exception):
    """Signed in, but the account is not tied to a person — the cabinet has nothing
    to show and the handler explains that instead of failing."""


def require_employee(user: Annotated[User, Depends(require_user)]) -> User:
    """Any signed in account may open the cabinet; it needs a linked person."""
    if user.employee_id is None or user.employee is None:
        raise NoEmployeeLinked()
    return user


AnyUser = Annotated[User, Depends(require_user)]
CabinetUser = Annotated[User, Depends(require_employee)]
ViewerUser = Annotated[User, Depends(require_role(UserRole.VIEWER))]
EditorUser = Annotated[User, Depends(require_role(UserRole.EDITOR))]
AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
DbSession = Annotated[Session, Depends(get_db)]
