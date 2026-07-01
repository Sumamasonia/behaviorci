from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.database import init_db
from app.config import settings
from app.auth import _RedirectException
from app.routers import projects, suites, runs, dashboard

app = FastAPI(
    title="BehaviorCI",
    description="The git diff for AI behavior. Behavioral regression testing for LLM-powered products.",
    version="1.0.0",
)

app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)


@app.exception_handler(_RedirectException)
async def redirect_exception_handler(request: Request, exc: _RedirectException):
    return RedirectResponse(url=exc.url, status_code=303)


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(suites.router)
app.include_router(runs.router)


@app.get("/health")
def health():
    return {"status": "ok"}