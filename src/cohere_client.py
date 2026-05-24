from __future__ import annotations

import os

import cohere


def get_client() -> cohere.Client | None:
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        return None
    return cohere.Client(api_key)


def summarize_spend(metrics_text: str) -> str:
    client = get_client()
    if client is None:
        return "Cohere API key is not configured. Add COHERE_API_KEY to .env to enable AI summaries."

    model = os.getenv("COHERE_MODEL", "command-r-plus")
    prompt = f"""
You are a concise personal finance analytics assistant.
Summarize the user's spending from the metrics below.
Do not invent numbers. Mention notable categories, anomalies, and recurring spend.

Metrics:
{metrics_text}
""".strip()

    response = client.chat(model=model, message=prompt)
    return response.text
