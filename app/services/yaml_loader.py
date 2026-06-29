"""
Loads test cases from version-controlled YAML files into the database.
This is the documented "developer-friendly" path: write YAML, commit it,
run `behaviorci sync` (see cli.py) to load it into the suite.
"""
import yaml
from sqlalchemy.orm import Session

from app import models


def load_yaml_suite(db: Session, project_id: str, yaml_path: str) -> models.TestSuite:
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    suite = db.query(models.TestSuite).filter_by(
        project_id=project_id, name=data["suite_name"]
    ).first()
    if not suite:
        suite = models.TestSuite(
            project_id=project_id,
            name=data["suite_name"],
            description=data.get("description", ""),
        )
        db.add(suite)
        db.commit()
        db.refresh(suite)

    # Replace test cases each sync so YAML is the source of truth
    db.query(models.TestCase).filter_by(suite_id=suite.id).delete()
    db.commit()

    for case in data["test_cases"]:
        db.add(models.TestCase(
            suite_id=suite.id,
            name=case["name"],
            input_prompt=case["input_prompt"],
            expected_behavior=case["expected_behavior"],
            criteria=case.get("criteria", {}),
            tags=case.get("tags", []),
        ))
    db.commit()
    db.refresh(suite)
    return suite
