from fastapi import FastAPI
from app.database import init_db
from app.routers import projects, suites, runs, dashboard

app = FastAPI(
    title="BehaviorCI",
    description="The git diff for AI behavior. Behavioral regression testing for LLM-powered products.",
    version="1.0.0",
)


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
