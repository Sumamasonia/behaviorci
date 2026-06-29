from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx

from app import models
from app.database import get_db
from app.auth import get_current_org, get_owned_suite, get_owned_run
from app.services.test_runner import run_suite

router = APIRouter(prefix="/api", tags=["runs"])


def _make_http_caller(target_url: str):
    def call(prompt: str) -> str:
        resp = httpx.post(target_url, json={"prompt": prompt}, timeout=60)
        resp.raise_for_status()
        return resp.json()["output"]
    return call


@router.post("/suites/{suite_id}/run")
async def trigger_run(
    suite_id: str,
    target_url: str,
    org: models.Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    get_owned_suite(suite_id, org, db)

    caller = _make_http_caller(target_url)
    try:
        run = await run_suite(db, suite_id, caller)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"run_id": run.id, "run_number": run.run_number, "status": run.status, "summary": run.summary}


@router.get("/suites/{suite_id}/runs")
def list_runs(suite_id: str, org: models.Organization = Depends(get_current_org), db: Session = Depends(get_db)):
    get_owned_suite(suite_id, org, db)
    runs = (
        db.query(models.SuiteRun)
        .filter_by(suite_id=suite_id)
        .order_by(models.SuiteRun.run_number.desc())
        .all()
    )
    return [{"id": r.id, "run_number": r.run_number, "status": r.status, "summary": r.summary} for r in runs]


@router.get("/runs/{run_id}")
def get_run(run_id: str, org: models.Organization = Depends(get_current_org), db: Session = Depends(get_db)):
    run = get_owned_run(run_id, org, db)
    results = db.query(models.TestResult).filter_by(suite_run_id=run.id).all()
    return {
        "id": run.id,
        "run_number": run.run_number,
        "status": run.status,
        "summary": run.summary,
        "results": [
            {
                "test_case_id": r.test_case_id,
                "output_text": r.output_text,
                "scores": r.scores,
                "passed": r.passed,
                "rationale": r.rationale,
            }
            for r in results
        ],
    }