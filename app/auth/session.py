from typing import Optional

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings
from app.models.user import User

COOKIE_NAME = "inv_session"

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="inventory-session")


def start_session(response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME,
        _serializer.dumps({"uid": user.id}),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        # the app runs over plain HTTP inside the LAN, so no Secure flag
    )


def end_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


def read_user_id(request: Request) -> Optional[int]:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        data = _serializer.loads(raw, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("uid")
