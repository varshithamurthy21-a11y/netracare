"""NetraCare API (FastAPI). Thin HTTP layer over backend.services."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import config, facts, services, triage
from .db import session
from .security import create_token, decode_token
from .seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed()
    yield


app = FastAPI(title="NetraCare API", version="1.0", lifespan=lifespan,
              description="AI front desk & care coordination for a fictional eye clinic.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(services.ServiceError)
async def service_error_handler(_: Request, exc: services.ServiceError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


def db():
    with session() as conn:
        yield conn


def current_user(authorization: str = Header(default=""), conn=Depends(db)) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    data = decode_token(token) if token else None
    user = services.get_user(conn, data["uid"]) if data else None
    if not user:
        raise HTTPException(401, "Please sign in again.")
    return user


# ---- schemas ------------------------------------------------------------
class RegisterIn(BaseModel):
    name: str
    email: str
    password: str
    phone: str = ""
    dob: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    name: str
    phone: str = ""
    dob: str = ""
    notes: str = ""


class BookIn(BaseModel):
    doctor_id: int
    date: str
    time: str
    reason: str = ""
    patient_id: int | None = None


class RescheduleIn(BaseModel):
    date: str
    time: str


class CompleteIn(BaseModel):
    visit_notes: str


class SummaryIn(BaseModel):
    summary: str
    publish: bool = False


class TextIn(BaseModel):
    text: str


class WalkInIn(BaseModel):
    name: str
    phone: str = ""
    email: str = ""


class StaffIn(BaseModel):
    role: str
    name: str
    email: str
    password: str


class DoctorIn(BaseModel):
    name: str
    email: str
    password: str
    specialty: str
    focus: str = ""
    bio: str = ""
    years: int = 5
    room: str = ""
    languages: str = "English"
    accent: str = "#6C5CE7"


class ActiveIn(BaseModel):
    active: bool


# ---- public -------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "clinic": "NetraCare", "disclaimer": config.DISCLAIMER}


@app.post("/auth/register")
def register(body: RegisterIn, conn=Depends(db)):
    user = services.register_patient(conn, body.name, body.email, body.password, body.phone, body.dob)
    return {"token": create_token(user["id"], user["role"]), "user": user}


@app.post("/auth/login")
def login(body: LoginIn, conn=Depends(db)):
    user = services.authenticate(conn, body.email, body.password)
    return {"token": create_token(user["id"], user["role"]), "user": user}


@app.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@app.put("/auth/me")
def update_me(body: ProfileIn, user=Depends(current_user), conn=Depends(db)):
    return services.update_profile(conn, user, body.name, body.phone, body.dob, body.notes)


@app.get("/doctors")
def doctors(conn=Depends(db)):
    return services.list_doctors(conn)


@app.get("/fact")
def fact():
    return facts.fact_of_the_day()


# ---- slots & appointments ----------------------------------------------
@app.get("/doctors/{doctor_id}/slots")
def slots(doctor_id: int, date: str, user=Depends(current_user), conn=Depends(db)):
    return services.get_slots(conn, doctor_id, date)


@app.post("/appointments")
def book(body: BookIn, user=Depends(current_user), conn=Depends(db)):
    return services.book(conn, user, body.doctor_id, body.date, body.time, body.reason, body.patient_id)


@app.get("/appointments")
def appointments(date: str | None = None, status: str | None = None, scope: str | None = None,
                 user=Depends(current_user), conn=Depends(db)):
    return services.list_appointments(conn, user, date, status, scope)


@app.get("/appointments/{appt_id}")
def appointment(appt_id: int, user=Depends(current_user), conn=Depends(db)):
    return services.get_appointment(conn, appt_id, user)


@app.post("/appointments/{appt_id}/cancel")
def cancel(appt_id: int, user=Depends(current_user), conn=Depends(db)):
    return services.cancel(conn, user, appt_id)


@app.post("/appointments/{appt_id}/reschedule")
def reschedule(appt_id: int, body: RescheduleIn, user=Depends(current_user), conn=Depends(db)):
    return services.reschedule(conn, user, appt_id, body.date, body.time)


@app.post("/appointments/{appt_id}/check-in")
def check_in(appt_id: int, user=Depends(current_user), conn=Depends(db)):
    return services.check_in(conn, user, appt_id)


@app.post("/appointments/{appt_id}/no-show")
def no_show(appt_id: int, user=Depends(current_user), conn=Depends(db)):
    return services.mark_no_show(conn, user, appt_id)


@app.post("/appointments/{appt_id}/review-flag")
def review_flag(appt_id: int, user=Depends(current_user), conn=Depends(db)):
    return services.dismiss_red_flag(conn, user, appt_id)


@app.post("/appointments/{appt_id}/complete")
def complete(appt_id: int, body: CompleteIn, user=Depends(current_user), conn=Depends(db)):
    return services.complete_visit(conn, user, appt_id, body.visit_notes)


@app.put("/appointments/{appt_id}/summary")
def summary(appt_id: int, body: SummaryIn, user=Depends(current_user), conn=Depends(db)):
    return services.save_summary(conn, user, appt_id, body.summary, body.publish)


@app.post("/appointments/{appt_id}/summary/regenerate")
def regen(appt_id: int, user=Depends(current_user), conn=Depends(db)):
    return services.regenerate_summary(conn, user, appt_id)


@app.get("/queue")
def queue(user=Depends(current_user), conn=Depends(db)):
    services.require_role(user, "frontdesk", "admin", "doctor")
    return services.queue(conn)


@app.get("/queue/me")
def my_queue(user=Depends(current_user), conn=Depends(db)):
    return services.my_queue_status(conn, user) or {}


# ---- triage helpers -----------------------------------------------------
@app.post("/triage/red-flags")
def red_flags(body: TextIn, user=Depends(current_user)):
    return triage.detect_red_flags(body.text)


@app.post("/triage/route")
def route(body: TextIn, user=Depends(current_user), conn=Depends(db)):
    result = triage.route_to_specialty(body.text)
    match = [d for d in services.list_doctors(conn) if d["specialty"] == result["specialty"]]
    result["doctor_id"] = match[0]["id"] if match else None
    result["disclaimer"] = config.DISCLAIMER
    return result


# ---- staff --------------------------------------------------------------
@app.get("/patients")
def patients(q: str = "", user=Depends(current_user), conn=Depends(db)):
    return services.search_patients(conn, user, q)


@app.post("/patients")
def walk_in(body: WalkInIn, user=Depends(current_user), conn=Depends(db)):
    return services.create_patient(conn, user, body.name, body.phone, body.email)


# ---- admin --------------------------------------------------------------
@app.get("/admin/stats")
def stats(user=Depends(current_user), conn=Depends(db)):
    return services.stats(conn, user)


@app.get("/admin/users")
def users(user=Depends(current_user), conn=Depends(db)):
    return services.list_users(conn, user)


@app.post("/admin/users/{user_id}/active")
def user_active(user_id: int, body: ActiveIn, user=Depends(current_user), conn=Depends(db)):
    return services.set_user_active(conn, user, user_id, body.active)


@app.post("/admin/staff")
def add_staff(body: StaffIn, user=Depends(current_user), conn=Depends(db)):
    return services.create_staff(conn, user, body.role, body.name, body.email, body.password)


@app.get("/admin/doctors")
def admin_doctors(user=Depends(current_user), conn=Depends(db)):
    services.require_role(user, "admin")
    return services.list_doctors(conn, include_inactive=True)


@app.post("/admin/doctors")
def add_doctor(body: DoctorIn, user=Depends(current_user), conn=Depends(db)):
    return services.create_doctor(conn, user, **body.model_dump())


@app.post("/admin/doctors/{doctor_id}/active")
def doctor_active(doctor_id: int, body: ActiveIn, user=Depends(current_user), conn=Depends(db)):
    return services.set_doctor_active(conn, user, doctor_id, body.active)


@app.get("/admin/audit")
def audit(user=Depends(current_user), conn=Depends(db)):
    return services.audit(conn, user)
