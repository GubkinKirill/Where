"""The department's side of the requests: one list, a status and a short answer."""

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth.deps import DbSession, EditorUser, ViewerUser
from app.models.enums import RequestStatus
from app.models.request import EquipmentRequest
from app.services import requests as requests_service
from app.services.errors import ServiceError
from app.templating import redirect, render

router = APIRouter()

OPEN_ONLY = (RequestStatus.NEW, RequestStatus.IN_PROGRESS)


@router.get("/requests", response_class=HTMLResponse)
def request_list(request: Request, db: DbSession, user: ViewerUser) -> HTMLResponse:
    show = (request.query_params.get("show") or "open").strip()
    statuses = None if show == "all" else OPEN_ONLY
    return render(
        request,
        "requests/list.html",
        {
            "user": user,
            "requests": requests_service.listing(db, statuses=statuses),
            "show": show,
            "open_count": requests_service.open_count(db),
        },
    )


@router.post("/requests/{request_id}/status")
async def set_status(request_id: int, request: Request, db: DbSession, user: EditorUser):
    record = db.get(EquipmentRequest, request_id)
    if record is None:
        return redirect("/requests", flash="Заявка не найдена.", kind="warn")

    form = await request.form()
    status = _status_or_none(form.get("status"))
    if status is None:
        return redirect("/requests", flash="Неизвестный статус.", kind="warn")

    try:
        requests_service.set_status(
            db,
            request=record,
            status=status,
            resolution=form.get("resolution"),
            actor=user,
        )
    except ServiceError as exc:
        db.rollback()
        return redirect("/requests", flash=str(exc), kind="warn")
    db.commit()
    return redirect(
        f"/requests?show={form.get('show') or 'open'}",
        flash=f"Заявка {record.id}: {status.value}.",
    )


def _status_or_none(raw) -> Optional[RequestStatus]:
    try:
        return RequestStatus(raw)
    except (ValueError, TypeError):
        return None
