from datetime import date, datetime
from typing import Any, Optional
from urllib.parse import quote, unquote

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import i18n
from app.config import APP_DIR, settings
from app.models.enums import (
    ItemStatus,
    LocationKind,
    MovementReason,
    RequestKind,
    RequestStatus,
    UserRole,
)

FLASH_COOKIE = "flash"

templates = Jinja2Templates(directory=APP_DIR / "templates")


def _format_date(value: Optional[date]) -> str:
    return value.strftime("%d.%m.%Y") if value else "—"


def _format_datetime(value: Optional[datetime]) -> str:
    return value.strftime("%d.%m.%Y, %H:%M") if value else "—"


def _since(value: Optional[datetime]) -> str:
    """«2 года 5 месяцев» — how long an item has been sitting where it is."""
    if not value:
        return ""
    days = (datetime.now() - value).days
    if days < 1:
        return "сегодня"
    if days < 31:
        return f"{days} дн."
    months = days // 30
    if months < 12:
        return f"{months} мес."
    years, rest = divmod(months, 12)
    return f"{years} г. {rest} мес." if rest else f"{years} г."


templates.env.filters.update(
    status_label=i18n.status_label,
    location_kind_label=i18n.location_kind_label,
    location_kind_icon=i18n.location_kind_icon,
    reason_label=i18n.reason_label,
    role_label=i18n.role_label,
    role_hint=i18n.role_hint,
    request_kind_label=i18n.request_kind_label,
    request_status_label=i18n.request_status_label,
    storage_kind_label=i18n.storage_kind_label,
    d=_format_date,
    dt=_format_datetime,
    since=_since,
)

templates.env.globals.update(
    ItemStatus=ItemStatus,
    LocationKind=LocationKind,
    MovementReason=MovementReason,
    RequestKind=RequestKind,
    RequestStatus=RequestStatus,
    UserRole=UserRole,
    STATUS_LABELS=i18n.STATUS_LABELS,
    LOCATION_KIND_LABELS=i18n.LOCATION_KIND_LABELS,
    MOVEMENT_REASON_LABELS=i18n.MOVEMENT_REASON_LABELS,
    STORAGE_KIND_LABELS=i18n.STORAGE_KIND_LABELS,
    REQUEST_KIND_LABELS=i18n.REQUEST_KIND_LABELS,
    REQUEST_STATUS_LABELS=i18n.REQUEST_STATUS_LABELS,
    ROLE_LABELS=i18n.ROLE_LABELS,
    base_url=settings.base_url,
)


def render(
    request: Request,
    template: str,
    context: Optional[dict[str, Any]] = None,
    *,
    status_code: int = 200,
) -> HTMLResponse:
    data: dict[str, Any] = {"request": request}
    data.update(context or {})
    data.setdefault("user", None)

    raw_flash = request.cookies.get(FLASH_COOKIE)
    if raw_flash:
        kind, _, text = unquote(raw_flash).partition("|")
        data["flash"] = {"kind": kind or "ok", "text": text}

    response = templates.TemplateResponse(request, template, data, status_code=status_code)
    if raw_flash:
        response.delete_cookie(FLASH_COOKIE)
    return response


def redirect(url: str, *, flash: Optional[str] = None, kind: str = "ok") -> RedirectResponse:
    """POST/redirect/GET with an optional one-shot message carried in a cookie,
    so no message text — and no personal data — ever ends up in a URL."""
    response = RedirectResponse(url, status_code=303)
    if flash:
        response.set_cookie(
            FLASH_COOKIE,
            quote(f"{kind}|{flash}"),
            max_age=30,
            httponly=True,
            samesite="lax",
        )
    return response
