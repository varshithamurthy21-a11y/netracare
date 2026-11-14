import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FROZEN = datetime(2026, 11, 4, 10, 0, 0)  # a Wednesday, 10:00 clinic time


class Clock:
    def __init__(self, start: datetime):
        self.t = start

    def now(self) -> datetime:
        return self.t

    def advance(self, **kwargs) -> None:
        self.t += timedelta(**kwargs)


@pytest.fixture()
def clock(monkeypatch):
    from backend import services

    c = Clock(FROZEN)
    monkeypatch.setattr(services, "now", c.now)
    monkeypatch.setattr(services, "HASH_ROUNDS", 1000)  # keep tests fast
    return c


@pytest.fixture()
def conn(tmp_path, monkeypatch, clock):
    monkeypatch.setenv("NETRACARE_DB", str(tmp_path / "test.db"))
    from backend import db, seed

    db.init_db()
    connection = db.connect()
    seed.seed_if_empty(connection)
    yield connection
    connection.close()


@pytest.fixture()
def login_as(conn):
    from backend import services

    def _login(email: str, password: str) -> dict:
        return services.login(conn, email, password)["user"]

    return _login
