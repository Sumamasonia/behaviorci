"""
Six core tables, matching BehaviorCI's documented schema:
Organizations, Projects, Test Suites, Test Cases, Suite Runs, Test Results.
"""
import uuid
import secrets
import datetime as dt

from sqlalchemy import (
    Column, String, Text, Float, Boolean, Integer,
    ForeignKey, DateTime, JSON
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id() -> str:
    return str(uuid.uuid4())


def generate_api_key() -> str:
    return "bci_" + secrets.token_urlsafe(32)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    api_key = Column(String, unique=True, nullable=True, index=True, default=generate_api_key)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    projects = relationship("Project", back_populates="organization", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=gen_id)
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    organization = relationship("Organization", back_populates="projects")
    suites = relationship("TestSuite", back_populates="project", cascade="all, delete-orphan")


class TestSuite(Base):
    __tablename__ = "test_suites"

    id = Column(String, primary_key=True, default=gen_id)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    project = relationship("Project", back_populates="suites")
    test_cases = relationship("TestCase", back_populates="suite", cascade="all, delete-orphan")
    runs = relationship("SuiteRun", back_populates="suite", cascade="all, delete-orphan")


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(String, primary_key=True, default=gen_id)
    suite_id = Column(String, ForeignKey("test_suites.id"), nullable=False)
    name = Column(String, nullable=False)
    input_prompt = Column(Text, nullable=False)
    expected_behavior = Column(Text, nullable=False)
    criteria = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    suite = relationship("TestSuite", back_populates="test_cases")
    results = relationship("TestResult", back_populates="test_case", cascade="all, delete-orphan")


class SuiteRun(Base):
    __tablename__ = "suite_runs"

    id = Column(String, primary_key=True, default=gen_id)
    suite_id = Column(String, ForeignKey("test_suites.id"), nullable=False)
    run_number = Column(Integer, nullable=False)
    status = Column(String, default="pending")
    started_at = Column(DateTime, default=dt.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    summary = Column(JSON, default=dict)

    suite = relationship("TestSuite", back_populates="runs")
    results = relationship("TestResult", back_populates="suite_run", cascade="all, delete-orphan")


class TestResult(Base):
    __tablename__ = "test_results"

    id = Column(String, primary_key=True, default=gen_id)
    suite_run_id = Column(String, ForeignKey("suite_runs.id"), nullable=False)
    test_case_id = Column(String, ForeignKey("test_cases.id"), nullable=False)
    output_text = Column(Text, nullable=False)
    scores = Column(JSON, default=dict)
    rationale = Column(Text, default="")
    embedding = Column(JSON, nullable=True)
    passed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    suite_run = relationship("SuiteRun", back_populates="results")
    test_case = relationship("TestCase", back_populates="results")