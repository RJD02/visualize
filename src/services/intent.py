"""Conversation intent detection and reasoning."""
from __future__ import annotations

import json
import re
from typing import Dict

from openai import OpenAI

from src.utils.config import settings

INTENT_SYSTEM = (
    "You are a router. Classify the user request into one intent: "
    "explain, edit, regenerate, clarify. Return ONLY JSON: "
    "{\"intent\": \"...\", \"target_image_version\": number|null, \"notes\": \"...\"}"
)


def detect_intent(message: str) -> Dict[str, object]:
    if not settings.openai_api_key:
        return {"intent": "clarify", "target_image_version": None, "notes": "Missing API key"}
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": INTENT_SYSTEM},
            {"role": "user", "content": message},
        ],
        temperature=0.1,
    )
    raw = response.choices[0].message.content or "{}"
    match = re.search(r"\{[\s\S]*\}", raw)
    data = json.loads(match.group(0)) if match else {"intent": "clarify"}
    return {
        "intent": data.get("intent", "clarify"),
        "target_image_version": data.get("target_image_version"),
        "notes": data.get("notes", ""),
    }


def explain_architecture(plan: dict, message: str) -> str:
    if not settings.openai_api_key:
        return "Missing OPENAI_API_KEY."
    client = OpenAI(api_key=settings.openai_api_key)
    prompt = (
        "Explain the architecture based on this plan JSON. "
        "Answer the user's question concisely.\n\n"
        f"Plan: {json.dumps(plan)}\n\n"
        f"Question: {message}"
    )
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": "You are an architecture assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content or ""
