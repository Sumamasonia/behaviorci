from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import tempfile, os

from app import models, schemas
from app.database import get_db
from app.auth import get_current_org, get_owned_project, get_owned_suite
from app.services.yaml_loader import load_yaml_suite

router = APIRouter(prefix="/api", tags=["suites"])


@router.post("/suites")
def create_suite(
    payload: schemas.TestSuiteCreate,
    org: models.Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    get_owned_project(payload.project_id, org, db)
    suite = models.TestSuite(
        project_id=payload.project_id, name=payload.name, description=payload.description
    )
    db.add(suite)
    db.commit()
    db.refresh(suite)
    return {"id": suite.id, "name": suite.name}


@router.get("/suites")
def list_suites(
    project_id: str | None = None,
    org: models.Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.TestSuite)
        .join(models.Project, models.TestSuite.project_id == models.Project.id)
        .filter(models.Project.org_id == org.id)
    )
    if project_id:
        q = q.filter(models.TestSuite.project_id == project_id)
    return q.all()


@router.get("/suites/{suite_id}")
def get_suite(suite_id: str, org: models.Organization = Depends(get_current_org), db: Session = Depends(get_db)):
    suite = get_owned_suite(suite_id, org, db)
    return {
        "id": suite.id,
        "name": suite.name,
        "description": suite.description,
        "test_case_count": len(suite.test_cases),
    }


@router.post("/suites/{suite_id}/sync-yaml")
def sync_yaml(
    suite_id: str,
    file: UploadFile = File(...),
    org: models.Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    suite = get_owned_suite(suite_id, org, db)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name
    try:
        updated_suite = load_yaml_suite(db, suite.project_id, tmp_path)
    finally:
        os.unlink(tmp_path)
    return {"suite_id": updated_suite.id, "test_case_count": len(updated_suite.test_cases)}


@router.post("/test-cases")
def create_test_case(
    payload: schemas.TestCaseCreate,
    org: models.Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    get_owned_suite(payload.suite_id, org, db)
    tc = models.TestCase(
        suite_id=payload.suite_id,
        name=payload.name,
        input_prompt=payload.input_prompt,
        expected_behavior=payload.expected_behavior,
        criteria=payload.criteria.model_dump(),
        tags=payload.tags,
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return {"id": tc.id, "name": tc.name}


@router.get("/suites/{suite_id}/test-cases")
def list_test_cases(suite_id: str, org: models.Organization = Depends(get_current_org), db: Session = Depends(get_db)):
    get_owned_suite(suite_id, org, db)
    return db.query(models.TestCase).filter_by(suite_id=suite_id).all()