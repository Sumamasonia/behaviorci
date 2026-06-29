"""
Regression Diff Engine.

Compares Suite Run N against Suite Run N-1 and produces a structured
regression report -- "git diff for AI behavior". Detects:

1. Metric regression  -- any score dimension dropped more than threshold
2. Pass/fail flips    -- tests that passed before and fail now (most actionable)
3. Behavioral drift   -- output embedding moved further than threshold even
                         if scores stayed acceptable (tone/style/personality change)
4. Pattern detection  -- failures clustering around a shared tag, signaling
                         a systemic issue rather than isolated noise
"""
from collections import defaultdict

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services.evaluator import cosine_distance

DIMENSIONS = ["correctness", "hallucination", "format", "behavioral"]


def _results_by_case(db: Session, suite_run_id: str) -> dict[str, models.TestResult]:
    rows = db.query(models.TestResult).filter_by(suite_run_id=suite_run_id).all()
    return {r.test_case_id: r for r in rows}


def compare_runs(db: Session, run_a_id: str, run_b_id: str) -> dict:
    """run_a = older/previous run (N-1), run_b = newer run (N)."""
    results_a = _results_by_case(db, run_a_id)
    results_b = _results_by_case(db, run_b_id)

    shared_case_ids = set(results_a.keys()) & set(results_b.keys())

    metric_regressions = []
    pass_fail_flips = []
    behavioral_drift = []
    tag_failures = defaultdict(lambda: {"degraded": 0, "total": 0})

    for case_id in shared_case_ids:
        ra, rb = results_a[case_id], results_b[case_id]
        test_case = db.query(models.TestCase).filter_by(id=case_id).first()
        tags = test_case.tags if test_case and test_case.tags else []

        degraded_this_case = False

        # 1. Metric regression per dimension
        for dim in DIMENSIONS:
            score_a = (ra.scores or {}).get(dim)
            score_b = (rb.scores or {}).get(dim)
            if score_a is None or score_b is None:
                continue
            drop = score_a - score_b
            if drop > settings.regression_score_threshold:
                metric_regressions.append({
                    "test_case_id": case_id,
                    "test_case_name": test_case.name if test_case else case_id,
                    "dimension": dim,
                    "previous_score": round(score_a, 3),
                    "current_score": round(score_b, 3),
                    "drop": round(drop, 3),
                })
                degraded_this_case = True

        # 2. Pass/fail flips
        if ra.passed and not rb.passed:
            pass_fail_flips.append({
                "test_case_id": case_id,
                "test_case_name": test_case.name if test_case else case_id,
                "previous_output": ra.output_text[:300],
                "current_output": rb.output_text[:300],
            })
            degraded_this_case = True

        # 3. Behavioral drift via embedding distance, even when scores look fine
        if ra.embedding and rb.embedding:
            distance = cosine_distance(ra.embedding, rb.embedding)
            if distance > settings.drift_distance_threshold:
                behavioral_drift.append({
                    "test_case_id": case_id,
                    "test_case_name": test_case.name if test_case else case_id,
                    "embedding_distance": round(distance, 4),
                    "scores_looked_fine": not any(
                        m["test_case_id"] == case_id for m in metric_regressions
                    ),
                })

        # 4. Pattern detection bookkeeping
        for tag in tags:
            tag_failures[tag]["total"] += 1
            if degraded_this_case:
                tag_failures[tag]["degraded"] += 1

    systemic_patterns = [
        {
            "tag": tag,
            "degraded": counts["degraded"],
            "total": counts["total"],
            "degradation_rate": round(counts["degraded"] / counts["total"], 3),
        }
        for tag, counts in tag_failures.items()
        if counts["total"] >= 2 and (counts["degraded"] / counts["total"]) >= 0.5
    ]

    return {
        "compared_run_a": run_a_id,
        "compared_run_b": run_b_id,
        "shared_test_cases": len(shared_case_ids),
        "metric_regressions": metric_regressions,
        "pass_fail_flips": pass_fail_flips,
        "behavioral_drift": behavioral_drift,
        "systemic_patterns": systemic_patterns,
        "has_regressions": bool(metric_regressions or pass_fail_flips or systemic_patterns),
    }
