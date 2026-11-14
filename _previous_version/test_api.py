"""HTTP-level tests. They need FastAPI + httpx installed (see requirements.txt); otherwise skipped."""
from datetime import date, timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NETRACARE_DB", str(tmp_path / "api.db"))
    from backend.main import app

    with TestClient(app) as c:
        yield c


def auth(client, email, password):
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def next_weekday(min_days_ahead=14):
    d = date.today() + timedelta(days=min_days_ahead)
    while d.weekday() > 4:
        d += timedelta(days=1)
    return d.isoformat()


def test_health_and_public_doctor_list(client):
    assert client.get("/health").json()["status"] == "ok"
    docs = client.get("/doctors").json()
    assert len(docs) == 5 and "email" not in docs[0]


def test_protected_routes_need_a_token(client):
    assert client.get("/appointments/mine").status_code == 401
    assert client.get("/admin/stats").status_code == 401


def test_login_failure_and_validation_shape(client):
    bad = client.post("/auth/login", json={"email": "patient@netracare.demo", "password": "nope"})
    assert bad.status_code == 401 and bad.json()["detail"] == "Incorrect email or password."
    assert client.post("/auth/login", json={"email": "x"}).status_code == 422


def test_patient_booking_round_trip(client):
    headers = auth(client, "patient@netracare.demo", "patient123")
    day = next_weekday()
    slots = client.get("/doctors/1/slots", params={"date": day}).json()["slots"]
    free = next(s["time"] for s in slots if s["available"])
    booked = client.post("/appointments", headers=headers,
                         json={"doctor_id": 1, "date": day, "time": free, "reason": "Check-up"})
    assert booked.status_code == 201 and booked.json()["status"] == "booked"
    again = client.post("/appointments", headers=headers, json={"doctor_id": 1, "date": day, "time": free})
    assert again.status_code == 409
    cancelled = client.post(f"/appointments/{booked.json()['id']}/cancel", headers=headers)
    assert cancelled.json()["status"] == "cancelled"


def test_roles_are_enforced_over_http(client):
    patient = auth(client, "patient@netracare.demo", "patient123")
    assert client.get("/admin/stats", headers=patient).status_code == 403
    assert client.get("/frontdesk/board", headers=patient,
                      params={"date": date.today().isoformat()}).status_code == 403
    admin = auth(client, "admin@netracare.demo", "admin123")
    assert client.get("/admin/stats", headers=admin).json()["totals"]["doctors"] == 5
    doctor = auth(client, "ananya.rao@netracare.demo", "doctor123")
    assert client.get("/doctor/schedule", headers=doctor,
                      params={"date": date.today().isoformat()}).status_code == 200
