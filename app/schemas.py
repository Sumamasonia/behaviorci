from typing import Optional, Any
from pydantic import BaseModel


class OrganizationCreate(BaseModel):
    name: str
    slug: str


class ProjectCreate(BaseModel):
    org_id: Optional[str] = None
    name: str
    slug: str


class TestSuiteCreate(BaseModel):
    project_id: str
    name: str
    description: str = ""


class TestCaseCriteria(BaseModel):
    numeric: dict[str, float] = {}
    format: list[str] = []
    semantic: dict[str, Any] = {}
    behavioral: dict[str, str] = {}


class TestCaseCreate(BaseModel):
    suite_id: str
    name: str
    input_prompt: str
    expected_behavior: str
    criteria: TestCaseCriteria = TestCaseCriteria()
    tags: list[str] = []


class JudgeScores(BaseModel):
    correctness: float
    hallucination: float
    format: float
    behavioral: float
    rationale: str


class TestResultOut(BaseModel):
    id: str
    test_case_id: str
    output_text: str
    scores: dict
    rationale: str
    passed: bool

    class Config:
        from_attributes = True


class SuiteRunOut(BaseModel):
    id: str
    run_number: int
    status: str
    summary: dict

    class Config:
        from_attributes = True