"""
Multi-tenant access control.

Two auth mechanisms, both backed by the same Organization.api_key:
- get_current_org: API-key header auth for the REST API (/api/*)
- get_dashboard_org: session-cookie auth for the browser dashboard
"""
from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session

from app import models
from app.database import get_db


def get_current_org(
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> models.Organization:
    if not x_api_key:
        raise HTTPException(401, "Missing X-API-Key header. Create an organization via POST /api/organizations to get one.")

    org = db.query(models.Organization).filter_by(api_key=x_api_key).first()
    if not org:
        raise HTTPException(401, "Invalid API key.")
    return org


def get_owned_project(project_id: str, org: models.Organization, db: Session) -> models.Project:
    project = db.query(models.Project).filter_by(id=project_id, org_id=org.id).first()
    if not project:
        raise HTTPException(404, "Project not found.")
    return project


def get_owned_suite(suite_id: str, org: models.Organization, db: Session) -> models.TestSuite:
    suite = (
        db.query(models.TestSuite)
        .join(models.Project, models.TestSuite.project_id == models.Project.id)
        .filter(models.TestSuite.id == suite_id, models.Project.org_id == org.id)
        .first()
    )
    if not suite:
        raise HTTPException(404, "Suite not found.")
    return suite


def get_owned_run(run_id: str, org: models.Organization, db: Session) -> models.SuiteRun:
    run = (
        db.query(models.SuiteRun)
        .join(models.TestSuite, models.SuiteRun.suite_id == models.TestSuite.id)
        .join(models.Project, models.TestSuite.project_id == models.Project.id)
        .filter(models.SuiteRun.id == run_id, models.Project.org_id == org.id)
        .first()
    )
    if not run:
        raise HTTPException(404, "Run not found.")
    return run


def get_dashboard_org(request: Request, db: Session = Depends(get_db)):
    """Session-cookie based auth for the browser dashboard. Returns the
    logged-in organization, or redirects to /login if there's no valid
    session. Used as a dependency on every dashboard page route."""
    org_id = request.session.get("org_id")
    if not org_id:
        raise _redirect_to_login(request)

    org = db.query(models.Organization).filter_by(id=org_id).first()
    if not org:
        request.session.clear()
        raise _redirect_to_login(request)

    return org


class _RedirectException(Exception):
    """Raised internally to short-circuit a dependency into a redirect.
    Caught by an exception handler registered in main.py."""
    def __init__(self, url: str):
        self.url = url


def _redirect_to_login(request: Request) -> _RedirectException:
    next_url = str(request.url)
    return _RedirectException(f"/login?next={next_url}")