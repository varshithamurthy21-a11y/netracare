"""Optional LLM access. Returns None when no key / any failure, so callers fall back."""
import os

import requests


def generate(prompt: str, system: str = "", max_tokens: int = 300) -> str | None:
    g_key = os.getenv("GOOGLE_API_KEY")
    if g_key:
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": g_key},
                json={
                    "systemInstruction": {"parts": [{"text": system}]} if system else None,
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.4},
                },
                timeout=20,
            )
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            pass
    a_key = os.getenv("ANTHROPIC_API_KEY")
    if a_key:
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": a_key, "anthropic-version": "2023-06-01"},
                json={
                    "model": os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"),
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=20,
            )
            r.raise_for_status()
            return r.json()["content"][0]["text"].strip()
        except Exception:
            pass
    return None


def available() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
