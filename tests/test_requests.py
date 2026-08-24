"""Requests: the employee files them, the department answers."""

import pytest

from app.models.enums import RequestKind, RequestStatus
from app.services import requests as requests_service
from app.services.errors import ServiceError


def test_empty_text_is_refused(db, employee):
    with pytest.raises(ServiceError):
        requests_service.create(db, employee=employee, kind=RequestKind.NEED, text=" ")


def test_open_and_closed_are_told_apart(db, employee, actor):
    first = requests_service.create(
        db, employee=employee, kind=RequestKind.NEED, text="Нужен монитор"
    )
    second = requests_service.create(
        db, employee=employee, kind=RequestKind.BROKEN, text="Не включается"
    )
    db.flush()
    assert requests_service.open_count(db) == 2

    requests_service.set_status(
        db, request=second, status=RequestStatus.DONE, resolution="Выдали", actor=actor
    )
    db.flush()
    assert requests_service.open_count(db) == 1
    assert second.closed_at is not None
    assert second.closed_by_user_id == actor.id
    assert requests_service.open_of(db, employee) == [first]


def test_reopening_clears_the_closing_marks(db, employee, actor):
    request = requests_service.create(
        db, employee=employee, kind=RequestKind.NEED, text="Нужен монитор"
    )
    requests_service.set_status(db, request=request, status=RequestStatus.DONE, actor=actor)
    requests_service.set_status(
        db, request=request, status=RequestStatus.IN_PROGRESS, actor=actor
    )
    db.flush()
    assert request.closed_at is None
    assert request.closed_by_user_id is None


def test_only_the_author_withdraws_and_only_while_untouched(db, employee, actor):
    request = requests_service.create(
        db, employee=employee, kind=RequestKind.NEED, text="Нужен монитор"
    )
    requests_service.set_status(
        db, request=request, status=RequestStatus.IN_PROGRESS, actor=actor
    )
    db.flush()
    with pytest.raises(ServiceError):
        requests_service.withdraw(db, request=request, employee=employee)
