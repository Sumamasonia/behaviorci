"""
Multi-tenant access control.

Every organization gets an API key (generated automatically when the org is
created). All API routes below the organization level require that key in
an `X-API-Key` header, and every query is scoped to the calling
organization's own data -- a request with org A's key can never see org B's
projects, suites, runs, or results, regardless of IDs guessed or passed in.
"""
from fastapi import Depends, HTTPException, Header
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