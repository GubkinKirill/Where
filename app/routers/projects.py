"""Equipment seen through the project it belongs to.

Projects themselves are edited as a reference book (`/directories/projects`); these
two pages only read: the list with counts and the card with everything that came
with the project and where each piece is now.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth.deps import DbSession, ViewerUser
from app.services import projects as projects_service
from app.templating import render

router = APIRouter()


@router.get("/projects", response_class=HTMLResponse)
def project_list(request: Request, db: DbSession, user: ViewerUser) -> HTMLResponse:
    projects = projects_service.list_projects(db)
    counts = projects_service.item_counts(db)
    return render(
        request,
        "projects/list.html",
        {
            "user": user,
            "projects": projects,
            "counts": counts,
            "company_count": projects_service.company_owned_count(db),
            "project_count": projects_service.project_owned_count(db),
        },
    )


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_card(
    project_id: int, request: Request, db: DbSession, user: ViewerUser
) -> HTMLResponse:
    project = projects_service.get_project(db, project_id)
    if project is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "projects/card.html",
        {
            "user": user,
            "project": project,
            "summary": projects_service.summary(db, project),
            "trips": projects_service.trips_of(db, project),
        },
    )
