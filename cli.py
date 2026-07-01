#!/usr/bin/env python3
"""
BehaviorCI CLI.

Usage:
    python cli.py init                                  # create DB tables + a default org/project, prints API key
    python cli.py get-api-key [slug]                     # print (or generate) an org's API key, default slug "default"
    python cli.py sync test_cases/my_suite.yaml          # load a YAML suite into the DB
    python cli.py run <suite_id> <target_url>            # run a suite against your model endpoint
    python cli.py report <run_id>                        # print a regression report to the terminal
"""
import asyncio
import json
import sys

from app.database import SessionLocal, init_db
from app import models
from app.services.yaml_loader import load_yaml_suite
from app.services.test_runner import run_suite
import httpx


def cmd_init():
    init_db()
    db = SessionLocal()
    org = db.query(models.Organization).filter_by(slug="default").first()
    if not org:
        org = models.Organization(name="Default Org", slug="default")
        db.add(org)
        db.commit()
        db.refresh(org)
    if not org.api_key:
        org.api_key = models.generate_api_key()
        db.commit()
        db.refresh(org)
    project = db.query(models.Project).filter_by(slug="default").first()
    if not project:
        project = models.Project(org_id=org.id, name="Default Project", slug="default")
        db.add(project)
        db.commit()
        db.refresh(project)
    print(f"Initialized. project_id={project.id}")
    print(f"API key (needed for API requests, e.g. via curl or /docs): {org.api_key}")
    db.close()


def cmd_get_api_key(slug: str = "default"):
    db = SessionLocal()
    org = db.query(models.Organization).filter_by(slug=slug).first()
    if not org:
        print(f"No organization with slug '{slug}'. Run `python cli.py init` first.")
        sys.exit(1)
    if not org.api_key:
        org.api_key = models.generate_api_key()
        db.commit()
    print(org.api_key)
    db.close()


def cmd_sync(yaml_path: str):
    db = SessionLocal()
    project = db.query(models.Project).filter_by(slug="default").first()
    if not project:
        print("Run `python cli.py init` first.")
        sys.exit(1)
    suite = load_yaml_suite(db, project.id, yaml_path)
    print(f"Synced suite '{suite.name}' (id={suite.id}) with {len(suite.test_cases)} test cases.")
    print(f"SUITE_ID={suite.id}")  # machine-parseable line for CI scripts to grep
    db.close()


def cmd_run(suite_id: str, target_url: str):
    db = SessionLocal()

    def caller(prompt: str) -> str:
        resp = httpx.post(target_url, json={"prompt": prompt}, timeout=600)
        resp.raise_for_status()
        return resp.json()["output"]

    run = asyncio.run(run_suite(db, suite_id, caller))
    print(f"Run #{run.run_number} completed. Summary:")
    print(json.dumps(run.summary, indent=2, default=str))

    report = run.summary.get("regression_report")
    if report and report.get("has_regressions"):
        print("\n!! REGRESSIONS DETECTED !!")
        sys.exit(1)
    db.close()


def cmd_report(run_id: str):
    db = SessionLocal()
    run = db.query(models.SuiteRun).filter_by(id=run_id).first()
    if not run:
        print("Run not found.")
        sys.exit(1)
    print(json.dumps(run.summary, indent=2, default=str))
    db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1]
    if command == "init":
        cmd_init()
    elif command == "get-api-key":
        cmd_get_api_key(sys.argv[2] if len(sys.argv) > 2 else "default")
    elif command == "sync":
        cmd_sync(sys.argv[2])
    elif command == "run":
        cmd_run(sys.argv[2], sys.argv[3])
    elif command == "report":
        cmd_report(sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)