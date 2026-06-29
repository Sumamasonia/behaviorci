from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.auth import get_current_org

router = APIRouter(prefix="/api", tags=["projects"])


@router.post("/organizations")
def create_org(payload: schemas.OrganizationCreate, db: Session = Depends(get_db)):
    if db.query(models.Organization).filter_by(slug=payload.slug).first():
        raise HTTPException(409, "An organization with that slug already exists.")
    org = models.Organization(name=payload.name, slug=payload.slug)
    db.add(org)
    db.commit()
    db.refresh(org)
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "api_key": org.api_key,
        "note": "Save this API key now -- it will not be shown again.",
    }


@router.get("/organizations/me")
def get_my_org(org: models.Organization = Depends(get_current_org)):
    return {"id": org.id, "name": org.name, "slug": org.slug}


@router.post("/projects")
def create_project(
    payload: schemas.ProjectCreate,
    org: models.Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    if payload.org_id and payload.org_id != org.id:
        raise HTTPException(403, "org_id does not match your API key's organization.")
    project = models.Project(org_id=org.id, name=payload.name, slug=payload.slug)
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "name": project.name, "slug": project.slug}


@router.get("/projects")
def list_projects(org: models.Organization = Depends(get_current_org), db: Session = Depends(get_db)):
    return db.query(models.Project).filter_by(org_id=org.id).all()