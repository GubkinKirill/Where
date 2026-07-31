from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Annotated

from app.auth.deps import CurrentUser, DbSession
from app.auth.providers import authenticate
from app.auth.session import end_session, start_session
from app.templating import render

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: CurrentUser, next: str = "/") -> HTMLResponse:
    if user is not None:
        return RedirectResponse(next, status_code=303)
    return render(request, "login.html", {"next": next})


@router.post("/login")
def login(
    request: Request,
    db: DbSession,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "/",
):
    user = authenticate(db, username, password)
    if user is None:
        # deliberately vague: do not reveal whether the login exists
        return render(
            request,
            "login.html",
            {"error": "Неверный логин или пароль.", "next": next, "username": username},
            status_code=401,
        )
    db.commit()
    response = RedirectResponse(next or "/", status_code=303)
    start_session(response, user)
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    end_session(response)
    return response
