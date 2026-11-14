"""Tiny HTTP client for the NetraCare API."""
from __future__ import annotations

import os
from typing import Any, Optional

import requests

API_URL = os.environ.get("NETRACARE_API", "http://127.0.0.1:8000").rstrip("/")


class ApiError(Exception):
    """A friendly, displayable error. status == 0 means the server could not be reached."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.message = message
        self.status = status


def _detail(resp: requests.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text[:200] or f"Something went wrong (error {resp.status_code})."
    detail = data.get("detail") if isinstance(data, dict) else None
    if isinstance(detail, list):  # FastAPI request-validation errors
        parts = []
        for item in detail:
            where = ".".join(str(p) for p in item.get("loc", [])[1:])
            parts.append(f"{where}: {item.get('msg')}" if where else str(item.get("msg")))
        return "; ".join(parts) or "Please check the details you entered."
    return str(detail) if detail else f"Something went wrong (error {resp.status_code})."


def request(method: str, path: str, token: Optional[str] = None, params: Optional[dict] = None,
            json: Optional[dict] = None) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = requests.request(method, f"{API_URL}{path}", headers=headers, params=params,
                                json=json, timeout=15)
    except requests.RequestException as exc:
        raise ApiError("Can't reach the NetraCare server. Is the backend running?", 0) from exc
    if resp.status_code >= 400:
        raise ApiError(_detail(resp), resp.status_code)
    return resp.json()
