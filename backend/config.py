"""Central settings for NetraCare."""
import os
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("NETRACARE_DB", BASE_DIR / "netracare.db"))
SECRET = os.getenv("NETRACARE_SECRET", "netracare-dev-secret-change-me")
TOKEN_TTL_SECONDS = 60 * 60 * 12
TZ = ZoneInfo(os.getenv("NETRACARE_TZ", "Asia/Kolkata"))

SLOT_MINUTES = 30
# Clinic hours: Monday-Saturday, two sessions per day (Sunday closed)
SESSIONS = [(time(9, 0), time(13, 0)), (time(14, 30), time(18, 0))]
OPEN_WEEKDAYS = {0, 1, 2, 3, 4, 5}
BOOKING_WINDOW_DAYS = 14
MAX_UPCOMING_PER_PATIENT = 3
AVG_CONSULT_MINUTES = 12  # used for the live wait-time estimate

ROLES = ("patient", "doctor", "frontdesk", "admin")
ACTIVE_STATUSES = ("booked", "checked_in", "completed")  # occupy a slot

DISCLAIMER = (
    "NetraCare's assistant helps with scheduling and logistics only. It does not "
    "give medical advice, diagnosis or treatment guidance."
)
