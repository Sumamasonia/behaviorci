"""
The Evaluator Agent.
"""
import json
import re
import threading
from functools import lru_cache

import numpy as np

from app.config import settings

JUDGE_SYSTEM_PROMPT = """You are a strict, consistent evaluator of AI model outputs.
You will be given:
- The input prompt sent to a model
- The model's actual output
- A description of the expected behavior
- Specific criteria to check

Score the output from 0.0 to 1.0 on each of these four dimensions:
- correctness: Is the factual/logical content accurate and complete relative to what was asked?
- hallucination: Score 1.0 if NO fabricated/unsupported claims are present, lower if they are.
- format: Does the output follow the required structural/format rules?
- behavioral: Does the tone, style, and reasoning approach match the expected behavior?

Respond with ONLY a JSON object, no other text, no markdown fences, in exactly this shape:
{"correctness": <float 0-1>, "hallucination": <float 0-1>, "format": <float 0-1>, "behavioral": <float 0-1>, "rationale": "<one or two sentence explanation>"}
"""


def _build_user_prompt(input_prompt: str, output: str, expected_behavior: str, criteria: dict) -> str:
    return (
        f"INPUT PROMPT SENT TO MODEL:\n{input_prompt}\n\n"
        f"MODEL'S ACTUAL OUTPUT:\n{output}\n\n"
        f"EXPECTED BEHAVIOR:\n{expected_behavior}\n\n"
        f"CRITERIA TO CHECK:\n{json.dumps(criteria, indent=2)}\n\n"
        "Return the JSON scoring object now."
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Judge did not return valid JSON: {text[:200]}")
    return json.loads(match.group(0))


def _validate_scores(data: dict) -> dict:
    required = ["correctness", "hallucination", "format", "behavioral"]
    for key in required:
        if key not in data:
            raise ValueError(f"Judge response missing '{key}'")
        data[key] = max(0.0, min(1.0, float(data[key])))
    data.setdefault("rationale", "")
    return data


def _judge_ollama(user_prompt: str) -> dict:
    import ollama

    client = ollama.Client(host=settings.ollama_host)
    response = client.chat(
        model=settings.ollama_model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        options={"temperature": 0},
    )
    return _extract_json(response["message"]["content"])


def _judge_anthropic(user_prompt: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return _extract_json(response.content[0].text)


def _judge_openai(user_prompt: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return _extract_json(response.choices[0].message.content)


def llm_judge(input_prompt: str, output: str, expected_behavior: str, criteria: dict) -> dict:
    user_prompt = _build_user_prompt(input_prompt, output, expected_behavior, criteria)

    backends = {
        "ollama": _judge_ollama,
        "anthropic": _judge_anthropic,
        "openai": _judge_openai,
    }
    backend = backends.get(settings.judge_mode)
    if backend is None:
        raise ValueError(f"Unknown JUDGE_MODE: {settings.judge_mode}")

    raw = backend(user_prompt)
    return _validate_scores(raw)


_embed_lock = threading.Lock()


@lru_cache(maxsize=1)
def _local_embed_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embed_local_model)


def _embed_local(text: str) -> list[float]:
    model = _local_embed_model()
    with _embed_lock:
        vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def warm_up_local_embedding_model():
    if settings.embed_mode == "local":
        _local_embed_model()


def _embed_openai(text: str) -> list[float]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(model="text-embedding-3-small", input=text)
    return response.data[0].embedding


def embed(text: str) -> list[float]:
    if settings.embed_mode == "local":
        return _embed_local(text)
    elif settings.embed_mode == "openai":
        return _embed_openai(text)
    raise ValueError(f"Unknown EMBED_MODE: {settings.embed_mode}")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def cosine_distance(a: list[float], b: list[float]) -> float:
    return 1.0 - cosine_similarity(a, b)


def check_semantic_similarity(output: str, expected_behavior: str) -> float:
    return cosine_similarity(embed(output), embed(expected_behavior))


def evaluate_case(input_prompt: str, output: str, expected_behavior: str, criteria: dict) -> dict:
    scores = llm_judge(input_prompt, output, expected_behavior, criteria)
    scores["semantic_similarity"] = check_semantic_similarity(output, expected_behavior)
    scores["embedding"] = embed(output)
    return scores