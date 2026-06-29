"""
Test Runner Service.
"""
import asyncio
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session
from sqlalchemy import func

from app import models
from app.config import settings
from app.services.evaluator import evaluate_case, warm_up_local_embedding_model
from app.services.diff_engine import compare_runs
from app.services.alerts import send_regression_alerts

_executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_evaluations)


def _score_to_pass(scores: dict, criteria: dict) -> bool:
    numeric = (criteria or {}).get("numeric", {})
    for key, min_val in numeric.items():
        dim = key.replace("_min", "")
        if scores.get(dim, 0) < min_val:
            return False

    core = [scores.get(d, 0) for d in ("correctness", "hallucination", "format", "behavioral")]
    return (sum(core) / len(core)) >= 0.7


async def _run_one_case(test_case: models.TestCase, get_model_output) -> dict:
    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(_executor, get_model_output, test_case.input_prompt)
    scores = await loop.run_in_executor(
        _executor,
        evaluate_case,
        test_case.input_prompt,
        output,
        test_case.expected_behavior,
        test_case.criteria or {},
    )
    return {"test_case": test_case, "output": output, "scores": scores}


async def run_suite(db: Session, suite_id: str, get_model_output) -> models.SuiteRun:
    suite = db.query(models.TestSuite).filter_by(id=suite_id).first()
    if not suite:
        raise ValueError(f"No suite with id {suite_id}")

    test_cases = db.query(models.TestCase).filter_by(suite_id=suite_id).all()
    if not test_cases:
        raise ValueError("Suite has no test cases")

    warm_up_local_embedding_model()

    last_run_number = db.query(func.max(models.SuiteRun.run_number)).filter_by(suite_id=suite_id).scalar() or 0

    run = models.SuiteRun(suite_id=suite_id, run_number=last_run_number + 1, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    semaphore = asyncio.Semaphore(settings.max_concurrent_evaluations)

    async def bounded(tc):
        async with semaphore:
            return await _run_one_case(tc, get_model_output)

    results = await asyncio.gather(*[bounded(tc) for tc in test_cases], return_exceptions=True)

    passed_count = 0
    errors = []
    for res in results:
        if isinstance(res, Exception):
            errors.append(str(res))
            continue
        tc = res["test_case"]
        scores = res["scores"]
        embedding = scores.pop("embedding", None)
        passed = _score_to_pass(scores, tc.criteria or {})
        passed_count += int(passed)

        db.add(models.TestResult(
            suite_run_id=run.id,
            test_case_id=tc.id,
            output_text=res["output"],
            scores=scores,
            rationale=scores.get("rationale", ""),
            embedding=embedding,
            passed=passed,
        ))

    if errors:
        print(f"\n[BehaviorCI] {len(errors)} test case(s) failed with an error:")
        for e in errors:
            print(f"  - {e}")

    run.status = "completed"
    run.completed_at = dt.datetime.utcnow()
    run.summary = {
        "total": len(test_cases),
        "passed": passed_count,
        "pass_rate": round(passed_count / len(test_cases), 4) if test_cases else 0,
    }
    db.commit()

    previous_run = (
        db.query(models.SuiteRun)
        .filter(models.SuiteRun.suite_id == suite_id, models.SuiteRun.run_number == run.run_number - 1)
        .first()
    )
    if previous_run:
        report = compare_runs(db, previous_run.id, run.id)
        run.summary = {**run.summary, "regression_report": report}
        db.commit()

        if report.get("has_regressions"):
            alert_status = send_regression_alerts(suite.name, run.run_number, run.id, report)
            if alert_status.get("slack"):
                print("[BehaviorCI] Slack alert sent.")
            if alert_status.get("email"):
                print("[BehaviorCI] Email alert sent.")

    db.refresh(run)
    return run