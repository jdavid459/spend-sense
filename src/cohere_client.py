from __future__ import annotations

import os

import requests


def summarize_spend(metrics_text: str) -> str:
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        return "Cohere API key is not configured. Add COHERE_API_KEY to .env to enable AI summaries."

    model = os.getenv("COHERE_MODEL", "command-r-plus")
    prompt = f"""
You are a concise personal finance analytics assistant.
Summarize the user's spending from the metrics below.
Do not invent numbers. Mention notable categories, anomalies, and recurring spend.

Metrics:
{metrics_text}
""".strip()

    response = requests.post(
        "https://api.cohere.com/v2/chat",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload.get("message", {}).get("content", [])
    text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
    return "\n".join(text_parts).strip() or "No summary returned from Cohere."
