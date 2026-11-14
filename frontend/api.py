"""Tiny client for the NetraCare API."""
import os

import requests

BASE = os.getenv("NETRACARE_API", "http://127.0.0.1:8000")


class ApiError(Exception):
    pass


class Client:
    def __init__(self, token: str | None = None):
        self.token = token

    def _call(self, method: str, path: str, **kw):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            r = requests.request(method, BASE + path, headers=headers, timeout=25, **kw)
        except requests.RequestException:
            raise ApiError("Can't reach the NetraCare server. Start it with:  uvicorn backend.main:app --reload")
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            if isinstance(detail, list):  # FastAPI validation errors
                detail = "; ".join(str(d.get("msg", d)) for d in detail)
            raise ApiError(str(detail))
        return r.json()

    get = lambda self, p, **params: self._call("GET", p, params=params or None)
    post = lambda self, p, body=None: self._call("POST", p, json=body or {})
    put = lambda self, p, body=None: self._call("PUT", p, json=body or {})
