"""Requests from employees. The department sees them in one list and closes them
with a short answer; nothing here moves equipment — that is still the movement log."""

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import now
from app.models.directory import Employee
from app.models.enums import RequestKind, RequestStatus
from app.models.item import Item
from app.models.request import EquipmentRequest
from app.models.user import User
from app.services.errors import ServiceError

MAX_OPEN_PER_EMPLOYEE = 20


def create(
    db: Session,
    *,
    employee: Employee,
    kind: RequestKind,
    text: str,
    item: Optional[Item] = None,
) -> EquipmentRequest:
    text = (text or "").strip()
    if len(text) < 5:
        raise ServiceError("Опишите, что нужно, хотя бы одной фразой.")
    if len(open_of(db, employee)) >= MAX_OPEN_PER_EMPLOYEE:
        raise ServiceError("Слишком много открытых заявок. Дождитесь ответа по прежним.")

    request = EquipmentRequest(
        employee_id=employee.id,
        kind=kind,
        text=text[:2000],
        item_id=item.id if item is not None else None,
    )
    db.add(request)
    db.flush()
    return request


def of_employee(db: Session, employee: Employee) -> list[EquipmentRequest]:
    return list(
        db.scalars(
            select(EquipmentRequest)
            .where(EquipmentRequest.employee_id == employee.id)
            .order_by(EquipmentRequest.created_at.desc(), EquipmentRequest.id.desc())
        )
    )


def open_of(db: Session, employee: Employee) -> list[EquipmentRequest]:
    return [request for request in of_employee(db, employee) if request.is_open]


def listing(
    db: Session, *, statuses: Optional[Sequence[RequestStatus]] = None
) -> list[EquipmentRequest]:
    query = select(EquipmentRequest)
    if statuses:
        query = query.where(EquipmentRequest.status.in_(list(statuses)))
    return list(
        db.scalars(
            query.order_by(EquipmentRequest.created_at.desc(), EquipmentRequest.id.desc())
        )
    )


def open_count(db: Session) -> int:
    return db.scalar(
        select(func.count(EquipmentRequest.id)).where(
            EquipmentRequest.status.in_([RequestStatus.NEW, RequestStatus.IN_PROGRESS])
        )
    ) or 0


def set_status(
    db: Session,
    *,
    request: EquipmentRequest,
    status: RequestStatus,
    resolution: Optional[str] = None,
    actor: Optional[User] = None,
) -> EquipmentRequest:
    if request.status is status and not resolution:
        raise ServiceError("Статус не изменился.")

    request.status = status
    if resolution is not None:
        request.resolution = (resolution or "").strip()[:2000] or None
    if status.is_open:
        request.closed_at = None
        request.closed_by_user_id = None
    else:
        request.closed_at = now()
        request.closed_by_user_id = actor.id if actor else None
    db.flush()
    return request


def withdraw(db: Session, *, request: EquipmentRequest, employee: Employee) -> EquipmentRequest:
    """The author takes their own request back — only while nobody has answered it."""
    if request.employee_id != employee.id:
        raise ServiceError("Это заявка другого сотрудника.")
    if request.status is not RequestStatus.NEW:
        raise ServiceError("Заявку уже взяли в работу, отозвать нельзя.")
    request.status = RequestStatus.REJECTED
    request.resolution = "Отозвана сотрудником."
    request.closed_at = now()
    db.flush()
    return request
