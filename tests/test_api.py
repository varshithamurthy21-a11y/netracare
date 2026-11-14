"""HTTP-level smoke tests. Need FastAPI + httpx (see requirements.txt); skipped otherwise."""
from datetime import date, timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    from backend.main import app
    with TestClient(app) as c:
        yield c


def auth(client, email, password):
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def test_health_doctors_and_auth_required(client):
    assert client.get("/health").json()["status"] == "ok"
    assert len(client.get("/doctors").json()) == 5
    assert client.get("/appointments").status_code == 401
    assert client.get("/admin/stats").status_code == 401


def test_login_errors(client):
    bad = client.post("/auth/login", json={"email": "patient@netracare.demo", "password": "nope"})
    assert bad.status_code == 401 and bad.json()["detail"] == "Incorrect email or password."


def test_book_conflict_cancel_round_trip(client):
    h = auth(client, "patient@netracare.demo", "Patient@123")
    day = date.today() + timedelta(days=9)
    while day.weekday() == 6:
        day += timedelta(days=1)
    slots = client.get("/doctors/1/slots", params={"date": day.isoformat()}, headers=h).json()
    free = next(s["time"] for s in slots if s["available"])
    body = {"doctor_id": 1, "date": day.isoformat(), "time": free, "reason": "Check-up"}
    ok = client.post("/appointments", headers=h, json=body)
    assert ok.status_code == 200 and ok.json()["status"] == "booked"
    other = auth(client, "rahul@netracare.demo", "Patient@123")
    assert client.post("/appointments", headers=other, json=body).status_code == 409
    assert client.post(f"/appointments/{ok.json()['id']}/cancel", headers=h).json()["status"] == "cancelled"


def test_role_permissions(client):
    h = auth(client, "patient@netracare.demo", "Patient@123")
    assert client.get("/admin/users", headers=h).status_code == 403
    admin = auth(client, "admin@netracare.demo", "Admin@123")
    assert client.get("/admin/stats", headers=admin).status_code == 200
