from fastapi import APIRouter, Depends, Request, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import tempfile, os

from app import models
from app.database import get_db
from app.auth import get_dashboard_org
from app.services.trends import (
    get_pass_rate_history,
    get_dimension_score_history,
    render_sparkline_svg,
)
from app.services.yaml_loader import load_yaml_suite

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/welcome", response_class=HTMLResponse)
def landing_page(request: Request):
    with open("app/templates/landing.html", "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content=content)


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, error: str | None = None):
    return templates.TemplateResponse("setup.html", {"request": request, "error": error})


@router.post("/setup")
def setup_submit(
    request: Request,
    org_name: str = Form(...),
    org_slug: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(models.Organization).filter_by(slug=org_slug.strip()).first()
    if existing:
        return RedirectResponse(url="/setup?error=That+name+is+already+taken", status_code=303)
    org = models.Organization(name=org_name.strip(), slug=org_slug.strip())
    db.add(org)
    db.commit()
    db.refresh(org)
    project = models.Project(org_id=org.id, name=f"{org_name} Project", slug=f"{org_slug}-project")
    db.add(project)
    db.commit()
    request.session["org_id"] = org.id
    request.session["org_name"] = org.name
    request.session["api_key"] = org.api_key
    return RedirectResponse(url="/onboarding-complete", status_code=303)


@router.get("/onboarding-complete", response_class=HTMLResponse)
def onboarding_complete(request: Request, org: models.Organization = Depends(get_dashboard_org)):
    return templates.TemplateResponse("onboarding_complete.html", {"request": request, "org": org})


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str | None = None, next: str = "/"):
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "next": next})


@router.post("/login")
def login_submit(
    request: Request,
    api_key: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    org = db.query(models.Organization).filter_by(api_key=api_key.strip()).first()
    if not org:
        return RedirectResponse(url=f"/login?error=Invalid+API+key&next={next}", status_code=303)
    request.session["org_id"] = org.id
    request.session["org_name"] = org.name
    request.session["api_key"] = org.api_key
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
            "id": s.id, "name": s.name,
            "test_case_count": len(s.test_cases),
            "latest_run": latest_run,
            "run_count": len(history),
            "sparkline": sparkline,
        })
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "suites": suite_cards, "org": org}
    )


@router.get("/new-suite", response_class=HTMLResponse)
def new_suite_page(
    request: Request,
    org: models.Organization = Depends(get_dashboard_org),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        "new_suite.html", {"request": request, "org": org}
    )


@router.post("/new-suite")
def new_suite_submit(
    request: Request,
    suite_name: str = Form(...),
    suite_description: str = Form(""),
    org: models.Organization = Depends(get_dashboard_org),
    db: Session = Depends(get_db),
):
    project = db.query(models.Project).filter_by(org_id=org.id).first()
    if not project:
        raise HTTPException(400, "No project found.")
    suite = models.TestSuite(
        project_id=project.id,
        name=suite_name.strip(),
        description=suite_description.strip(),
    )
    db.add(suite)
    db.commit()
    db.refresh(suite)
    return RedirectResponse(url=f"/suite/{suite.id}/add-cases", status_code=303)


@router.get("/suite/{suite_id}/add-cases", response_class=HTMLResponse)
def add_cases_page(
    suite_id: str,
    request: Request,
    org: models.Organization = Depends(get_dashboard_org),
    db: Session = Depends(get_db),
):
    suite = (
        db.query(models.TestSuite)
        .join(models.Project)
        .filter(models.TestSuite.id == suite_id, models.Project.org_id == org.id)
        .first()
    )
    if not suite:
        raise HTTPException(404, "Suite not found")
    existing_cases = db.query(models.TestCase).filter_by(suite_id=suite_id).all()
    return templates.TemplateResponse(
        "add_cases.html", {
            "request": request, "org": org,
            "suite": suite, "existing_cases": existing_cases
        }
    )


@router.post("/suite/{suite_id}/add-case")
def add_case_submit(
    suite_id: str,
    request: Request,
    case_name: str = Form(...),
    input_prompt: str = Form(...),
    expected_behavior: str = Form(...),
    correctness_min: float = Form(0.8),
    tags: str = Form(""),
    org: models.Organization = Depends(get_dashboard_org),
    db: Session = Depends(get_db),
):
    suite = (
        db.query(models.TestSuite)
        .join(models.Project)
        .filter(models.TestSuite.id == suite_id, models.Project.org_id == org.id)
        .first()
    )
    if not suite:
        raise HTTPException(404, "Suite not found")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    tc = models.TestCase(
        suite_id=suite_id,
        name=case_name.strip(),
        input_prompt=input_prompt.strip(),
        expected_behavior=expected_behavior.strip(),
        criteria={"numeric": {"correctness_min": correctness_min}},
        tags=tag_list,
    )
    db.add(tc)
    db.commit()
    return RedirectResponse(url=f"/suite/{suite_id}/add-cases", status_code=303)

@router.post("/suite/{suite_id}/delete-case/{case_id}")
def delete_case(
    suite_id: str,
    case_id: str,
    org: models.Organization = Depends(get_dashboard_org),
    db: Session = Depends(get_db),
):
    suite = (
        db.query(models.TestSuite)
        .join(models.Project)
        .filter(models.TestSuite.id == suite_id, models.Project.org_id == org.id)
        .first()
    )
    if not suite:
        raise HTTPException(404, "Suite not found")
    tc = db.query(models.TestCase).filter_by(id=case_id, suite_id=suite_id).first()
    if tc:
        db.delete(tc)
        db.commit()
    return RedirectResponse(url=f"/suite/{suite_id}/add-cases", status_code=303)

@router.post("/suite/{suite_id}/upload-yaml")
def upload_yaml(
    suite_id: str,
    request: Request,
    yaml_file: UploadFile = File(...),
    org: models.Organization = Depends(get_dashboard_org),
    db: Session = Depends(get_db),
):
    suite = (
        db.query(models.TestSuite)
        .join(models.Project)
        .filter(models.TestSuite.id == suite_id, models.Project.org_id == org.id)
        .first()
    )
    if not suite:
        raise HTTPException(404, "Suite not found")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp:
        tmp.write(yaml_file.file.read())
        tmp_path = tmp.name
    try:
        load_yaml_suite(db, suite.project_id, tmp_path)
    finally:
        os.unlink(tmp_path)
    return RedirectResponse(url=f"/suite/{suite_id}/add-cases", status_code=303)


@router.get("/suite/{suite_id}", response_class=HTMLResponse)
def suite_detail(
    suite_id: str,
    request: Request,
    org: models.Organization = Depends(get_dashboard_org),
    db: Session = Depends(get_db),
):
    suite = (
        db.query(models.TestSuite)
        .join(models.Project)
        .filter(models.TestSuite.id == suite_id, models.Project.org_id == org.id)
        .first()
    )
    if not suite:
        raise HTTPException(404, "Suite not found")
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
            "org": org, "api_key": org.api_key,
            "test_case_count": len(suite.test_cases),
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
        .join(models.TestSuite)
        .join(models.Project)
        .filter(models.SuiteRun.id == run_id, models.Project.org_id == org.id)
        .first()
    )
    if not run:
        raise HTTPException(404, "Run not found")
    results = db.query(models.TestResult).filter_by(suite_run_id=run_id).all()
    enriched = []
    for r in results:
        tc = db.query(models.TestCase).filter_by(id=r.test_case_id).first()
        enriched.append({"result": r, "case_name": tc.name if tc else "Unknown"})
    return templates.TemplateResponse(
        "run_detail.html", {"request": request, "run": run, "results": enriched, "org": org}
    )