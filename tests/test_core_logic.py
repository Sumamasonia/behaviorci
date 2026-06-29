"""
Unit tests for the diff engine's pure logic. These don't require Ollama,
sentence-transformers, or any external service -- they test the regression
detection rules directly so you can verify the core logic for free, instantly.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.evaluator import cosine_similarity, cosine_distance


def test_cosine_similarity_identical_vectors():
    v = [1.0, 0.0, 0.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal_vectors():
    a, b = [1.0, 0.0], [0.0, 1.0]
    assert abs(cosine_similarity(a, b) - 0.0) < 1e-6


def test_cosine_distance_is_inverse_of_similarity():
    a, b = [1.0, 0.0], [0.0, 1.0]
    assert abs(cosine_distance(a, b) - (1 - cosine_similarity(a, b))) < 1e-6


def test_score_to_pass_respects_numeric_threshold():
    from app.services.test_runner import _score_to_pass

    scores = {"correctness": 0.9, "hallucination": 0.95, "format": 0.9, "behavioral": 0.9}
    criteria = {"numeric": {"correctness_min": 0.95}}
    assert _score_to_pass(scores, criteria) is False  # 0.9 < 0.95 threshold

    criteria_ok = {"numeric": {"correctness_min": 0.8}}
    assert _score_to_pass(scores, criteria_ok) is True
