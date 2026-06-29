"""
Trend data for the dashboard. Pure data + a small inline SVG renderer --
no JS charting library needed, so there's nothing extra to install or host.
"""
from sqlalchemy.orm import Session

from app import models

DIMENSIONS = ["correctness", "hallucination", "format", "behavioral"]


def get_pass_rate_history(db: Session, suite_id: str) -> list[dict]:
    runs = (
        db.query(models.SuiteRun)
        .filter_by(suite_id=suite_id, status="completed")
        .order_by(models.SuiteRun.run_number.asc())
        .all()
    )
    return [
        {"run_number": r.run_number, "pass_rate": (r.summary or {}).get("pass_rate", 0)}
        for r in runs
    ]


def get_dimension_score_history(db: Session, suite_id: str) -> dict[str, list[dict]]:
    runs = (
        db.query(models.SuiteRun)
        .filter_by(suite_id=suite_id, status="completed")
        .order_by(models.SuiteRun.run_number.asc())
        .all()
    )
    history = {dim: [] for dim in DIMENSIONS}
    for run in runs:
        results = db.query(models.TestResult).filter_by(suite_run_id=run.id).all()
        for dim in DIMENSIONS:
            scores = [r.scores.get(dim) for r in results if r.scores and dim in r.scores]
            avg = round(sum(scores) / len(scores), 3) if scores else None
            if avg is not None:
                history[dim].append({"run_number": run.run_number, "avg_score": avg})
    return history


def render_sparkline_svg(points: list[float], width: int = 280, height: int = 60,
                          color: str = "#3fb950", fill: bool = True) -> str:
    if not points:
        return f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg"></svg>'

    if len(points) == 1:
        points = points * 2

    pad = 6
    n = len(points)
    step = (width - 2 * pad) / (n - 1)
    coords = []
    for i, v in enumerate(points):
        x = pad + i * step
        y = pad + (1 - max(0.0, min(1.0, v))) * (height - 2 * pad)
        coords.append((round(x, 1), round(y, 1)))

    path_d = "M " + " L ".join(f"{x},{y}" for x, y in coords)
    fill_d = ""
    if fill:
        fill_d = (
            f'<path d="{path_d} L {coords[-1][0]},{height - pad} '
            f'L {coords[0][0]},{height - pad} Z" fill="{color}" opacity="0.12" stroke="none" />'
        )

    dots = "".join(
        f'<circle cx="{x}" cy="{y}" r="2.5" fill="{color}" />' for x, y in coords
    )

    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:{height}px;">'
        f'{fill_d}'
        f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round" />'
        f'{dots}'
        f'</svg>'
    )