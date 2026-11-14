"""SQLite schema and connection helper."""
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('patient','doctor','frontdesk','admin')),
    active INTEGER NOT NULL DEFAULT 1,
    dob TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
    specialty TEXT NOT NULL,
    focus TEXT DEFAULT '',
    bio TEXT DEFAULT '',
    years INTEGER DEFAULT 5,
    room TEXT DEFAULT '',
    languages TEXT DEFAULT 'English',
    accent TEXT DEFAULT '#6C5CE7',
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES users(id),
    doctor_id INTEGER NOT NULL REFERENCES doctors(id),
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    reason TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'booked'
        CHECK (status IN ('booked','checked_in','completed','cancelled','no_show')),
    red_flag INTEGER NOT NULL DEFAULT 0,
    red_flag_reason TEXT DEFAULT '',
    visit_notes TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    summary_status TEXT NOT NULL DEFAULT 'none' CHECK (summary_status IN ('none','draft','published')),
    booked_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    checked_in_at TEXT
);
-- One live appointment per doctor/date/time: double booking is impossible at DB level.
CREATE UNIQUE INDEX IF NOT EXISTS uq_slot ON appointments(doctor_id, date, time)
    WHERE status IN ('booked','checked_in','completed');
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    actor_name TEXT,
    action TEXT NOT NULL,
    detail TEXT DEFAULT '',
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)
