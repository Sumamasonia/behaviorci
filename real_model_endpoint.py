"""
Real product endpoint -- replaces mock_model_endpoint.py.

This wraps an ACTUAL model so BehaviorCI is testing something real instead
of canned answers. Three backends, switch via .env, no code changes needed:

  PRODUCT_MODEL_BACKEND=ollama      <- free, local, default (e.g. llama3.1:8b)
  PRODUCT_MODEL_BACKEND=anthropic   <- requires ANTHROPIC_API_KEY, costs money
  PRODUCT_MODEL_BACKEND=openai      <- requires OPENAI_API_KEY, costs money

Run it the same way you ran the mock:
    uvicorn real_model_endpoint:app --port 9000

Then point BehaviorCI at it exactly like before:
    python cli.py run <suite_id> http://localhost:9000/generate

If you're testing YOUR OWN product (not a raw LLM call) -- e.g. a chatbot
with its own business logic, retrieval, prompt engineering, etc. -- replace
the body of `call_model()` below with a call into your actual product's
code or API instead of any of these three backends. The only contract
BehaviorCI cares about is: POST {"prompt": "..."} -> {"output": "..."}.
"""
import os
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

load_dotenv()  # this script reads os.environ directly, so .env needs to be loaded explicitly

app = FastAPI()

BACKEND = os.environ.get("PRODUCT_MODEL_BACKEND", "ollama")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("PRODUCT_OLLAMA_MODEL", os.environ.get("OLLAMA_MODEL", "llama3.1:8b"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

SYSTEM_PROMPT = os.environ.get(
    "PRODUCT_SYSTEM_PROMPT",
    "You are a helpful, friendly customer support assistant. Be concise, "
    "accurate, and professional. Do not make up information you don't have.",
)


def call_ollama(prompt: str) -> str:
    import ollama
    client = ollama.Client(host=OLLAMA_HOST)
    response = client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return response["message"]["content"]


def call_anthropic(prompt: str) -> str:
    import anthropic
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY is not set in .env")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def call_openai(prompt: str) -> str:
    from openai import OpenAI
    if not OPENAI_API_KEY:
        raise HTTPException(500, "OPENAI_API_KEY is not set in .env")
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content


def call_model(prompt: str) -> str:
    if BACKEND == "ollama":
        return call_ollama(prompt)
    elif BACKEND == "anthropic":
        return call_anthropic(prompt)
    elif BACKEND == "openai":
        return call_openai(prompt)
    raise HTTPException(500, f"Unknown PRODUCT_MODEL_BACKEND: {BACKEND}")


@app.post("/generate")
async def generate(payload: dict):
    prompt = payload.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "Missing 'prompt' in request body")
    output = call_model(prompt)
    return {"output": output}


@app.get("/health")
def health():
    return {"status": "ok", "backend": BACKEND, "model": OLLAMA_MODEL if BACKEND == "ollama" else BACKEND}