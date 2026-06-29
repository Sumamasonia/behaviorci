"""
A fake "product under test" -- stands in for your real model/API so you can
verify BehaviorCI's full pipeline (runner -> judge -> diff engine) works
correctly without needing any LLM API key for the thing being tested.

Usage:
    python mock_model_endpoint.py            # serves good, on-policy answers
    DEGRADE=1 python mock_model_endpoint.py   # serves worse answers on purpose,
                                               # so you can SEE the regression
                                               # diff engine catch it on a second run

Run on its own port, separate from the main BehaviorCI app:
    uvicorn mock_model_endpoint:app --port 9000
"""
import os
from fastapi import FastAPI

app = FastAPI()
DEGRADE = os.environ.get("DEGRADE") == "1"

GOOD_ANSWERS = {
    "how long do i have to request a refund?":
        "You have 30 days from the purchase date to request a refund. Let me know if you'd like help starting one!",
    "i bought the product 45 days ago as a gift for someone, can they still return it?":
        "Our standard window is 30 days, so this is a bit past that -- but gifts sometimes qualify for an exception. "
        "I can escalate this to our team to check, would you like me to do that?",
    "i can't log in, i think i forgot my password.":
        "No problem! Here's how to reset it: 1) Go to the login page and click 'Forgot password'. "
        "2) Enter your email. 3) Check your inbox for a reset link. 4) Choose a new password.",
    "my account says it's locked after too many failed login attempts. what do i do?":
        "That happens after several failed attempts as a security measure. You can unlock it by resetting your "
        "password from the login page -- it'll automatically lift the lock. I'm here if you need anything else.",
    "i was charged twice for my subscription this month.":
        "I'm sorry about that -- that's not supposed to happen. I'll flag this for our billing team to investigate, "
        "and any duplicate charge will be refunded. Thanks for letting us know.",
    "hi": "Hi there! How can I help you today?",
}

# Deliberately worse answers: vaguer, less correct, colder tone, sometimes
# invents details -- used to demonstrate the diff engine catching real issues.
DEGRADED_ANSWERS = {
    "how long do i have to request a refund?":
        "Refunds are evaluated case by case depending on several internal factors.",
    "i bought the product 45 days ago as a gift for someone, can they still return it?":
        "No, returns are not accepted after the window closes.",
    "i can't log in, i think i forgot my password.":
        "Try clearing your browser cache or contact IT support.",
    "my account says it's locked after too many failed login attempts. what do i do?":
        "Accounts get locked sometimes. Wait and try again later.",
    "i was charged twice for my subscription this month.":
        "Please check your bank statement, this is likely a bank error on their end.",
    "hi": "Hello.",
}


@app.post("/generate")
async def generate(payload: dict):
    prompt = payload.get("prompt", "").strip().lower()
    answers = DEGRADED_ANSWERS if DEGRADE else GOOD_ANSWERS
    output = answers.get(prompt, "I'm not sure how to help with that specific question, but I'll find out for you.")
    return {"output": output}
