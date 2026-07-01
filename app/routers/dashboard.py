from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.auth import get_dashboard_org
from app.services.trends import (
    get_pass_rate_history,
    get_dimension_score_history,
    render_sparkline_svg,
)

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str | None = None, next: str = "/"):
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": error, "next": next}
    )


@router.post("/login")
def login_submit(
    request: Request,
    api_key: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    org = db.query(models.Organization).filter_by(api_key=api_key.strip()).first()
    if not org:
        return RedirectResponse(
            url=f"/login?error=Invalid+API+key&next={next}", status_code=303
        )
    request.session["org_id"] = org.id
    request.session["org_name"] = org.name
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    return RedirectResponse(url=safe_next, status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    org: models.Organization = Depends(get_dashboard_org),
    db: Session = Depends(get_db),
):
    suites = (
        db.query(models.TestSuite)
        .join(models.Project, models.TestSuite.project_id == models.Project.id)
        .filter(models.Project.org_id == org.id)
        .all()
    )
    suite_cards = []
    for s in suites:
        latest_run = (
            db.query(models.SuiteRun)
            .filter_by(suite_id=s.id)
            .order_by(models.SuiteRun.run_number.desc())
            .first()
        )
        history = get_pass_rate_history(db, s.id)
        sparkline = render_sparkline_svg(
            [h["pass_rate"] for h in history], width=200, height=36
        ) if len(history) >= 2 else None
        suite_cards.append({
            "id": s.id,
            "name": s.name,
            "test_case_count": len(s.test_cases),
            "latest_run": latest_run,
            "run_count": len(history),
            "sparkline": sparkline,
        })
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "suites": suite_cards, "org": org}
    )


@router.get("/suite/{suite_id}", response_class=HTMLResponse)
def suite_detail(
    suite_id: str,
    request: Request,
    org: models.Organization = Depends(get_dashboard_org),
    db: Session = Depends(get_db),
):
    suite = (
        db.query(models.TestSuite)
        .join(models.Project, models.TestSuite.project_id == models.Project.id)
        .filter(models.TestSuite.id == suite_id, models.Project.org_id == org.id)
        .first()
    )
    if not suite:
        raise HTTPException(404, f"No suite found with id {suite_id} in your organization.")

    runs = (
        db.query(models.SuiteRun)
        .filter_by(suite_id=suite_id)
        .order_by(models.SuiteRun.run_number.desc())
        .all()
    )

    pass_rate_history = get_pass_rate_history(db, suite_id)
    pass_rate_chart = render_sparkline_svg(
        [h["pass_rate"] for h in pass_rate_history], width=600, height=120, color="#3fb950"
    ) if len(pass_rate_history) >= 2 else None

    dimension_history = get_dimension_score_history(db, suite_id)
    dimension_colors = {
        "correctness": "#58a6ff", "hallucination": "#d29922",
        "format": "#a371f7", "behavioral": "#3fb950",
    }
    dimension_charts = {}
    for dim, points in dimension_history.items():
        if len(points) >= 2:
            dimension_charts[dim] = render_sparkline_svg(
                [p["avg_score"] for p in points], width=280, height=70,
                color=dimension_colors.get(dim, "#58a6ff"), fill=False,
            )

    return templates.TemplateResponse(
        "suite_detail.html",
        {
            "request": request, "suite": suite, "runs": runs,
            "pass_rate_chart": pass_rate_chart,
            "dimension_charts": dimension_charts,
            "has_trend_data": len(pass_rate_history) >= 2,
            "org": org,
        },
    )


@router.get("/run/{run_id}", response_class=HTMLResponse)
def run_detail(
    run_id: str,
    request: Request,
    org: models.Organization = Depends(get_dashboard_org),
    db: Session = Depends(get_db),
):
    run = (
        db.query(models.SuiteRun)
        .join(models.TestSuite, models.SuiteRun.suite_id == models.TestSuite.id)
        .join(models.Project, models.TestSuite.project_id == models.Project.id)
        .filter(models.SuiteRun.id == run_id, models.Project.org_id == org.id)
        .first()
    )
    if not run:
        raise HTTPException(404, f"No run found with id {run_id} in your organization.")

    results = db.query(models.TestResult).filter_by(suite_run_id=run_id).all()
    enriched = []
    for r in results:
        tc = db.query(models.TestCase).filter_by(id=r.test_case_id).first()
        enriched.append({"result": r, "case_name": tc.name if tc else "Unknown"})
    return templates.TemplateResponse(
        "run_detail.html", {"request": request, "run": run, "results": enriched, "org": org}
    )