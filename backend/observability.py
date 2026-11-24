"""Lightweight LLMOps: traces, spans, token + cost estimates.

Every assistant/agent request is recorded as a *trace* made of *spans* (guard, retrieve,
generate, tool ...). Traces live in the `traces` table (shown on the admin "Evals & Traces"
page). If the `opik` package is installed and configured, traces are mirrored to Opik too.
Token counts are estimates (~4 characters per token) unless a provider reports real usage.
"""
import contextvars
import datetime as dt
import json
import os
import time
import uuid
from contextlib import contextmanager

from . import config

# USD per 1M tokens (input, output). Estimates for budgeting; override with NETRACARE_PRICES='{"model":[in,out]}'
PRICES = {"gemini-2.0-flash": (0.10, 0.40), "claude-haiku-5-5": (1.00, 5.00), "default": (0.50, 1.50)}
try:
    PRICES.update({k: tuple(v) for k, v in json.loads(os.getenv("NETRACARE_PRICES", "{}")).items()})
except Exception:
    pass

_current: contextvars.ContextVar = contextvars.ContextVar("nc_trace", default=None)
_run_id: contextvars.ContextVar = contextvars.ContextVar("nc_run", default="")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def estimate_cost(model: str, tin: int, tout: int) -> float:
    pin, pout = PRICES.get(model, PRICES["default"])
    return (tin * pin + tout * pout) / 1_000_000


class Trace:
    def __init__(self, name: str, user_id: int | None, input: str):
        self.trace_id = uuid.uuid4().hex[:12]
        self.name, self.user_id, self.input = name, user_id, input
        self.output, self.intent, self.error = "", "", ""
        self.spans: list[dict] = []
        self.input_tokens = self.output_tokens = self.llm_calls = 0
        self.cost = 0.0
        self.t0 = time.perf_counter()

    @contextmanager
    def span(self, name: str, **meta):
        t = time.perf_counter()
        rec = {"name": name, "meta": meta}
        try:
            yield rec
        except Exception as exc:  # keep the failure visible in the trace, then re-raise
            rec["error"] = str(exc)
            raise
        finally:
            rec["ms"] = round((time.perf_counter() - t) * 1000, 2)
            self.spans.append(rec)

    def add_llm(self, model: str, prompt: str, output: str, ms: float) -> None:
        tin, tout = estimate_tokens(prompt), estimate_tokens(output)
        self.input_tokens += tin
        self.output_tokens += tout
        self.llm_calls += 1
        self.cost += estimate_cost(model, tin, tout)
        self.spans.append({"name": "llm", "ms": round(ms, 2), "meta": {"model": model, "in": tin, "out": tout}})


def current() -> Trace | None:
    return _current.get()


def record_llm(model: str, prompt: str, output: str, ms: float) -> None:
    t = _current.get()
    if t:
        t.add_llm(model, prompt, output, ms)


@contextmanager
def span(name: str, **meta):
    """Span on the active trace (no-op when none is active)."""
    t = _current.get()
    if t is None:
        yield {}
    else:
        with t.span(name, **meta) as rec:
            yield rec


@contextmanager
def run_context(run_id: str):
    token = _run_id.set(run_id)
    try:
        yield
    finally:
        _run_id.reset(token)


def _save(t: Trace, conn) -> None:
    row = (t.trace_id, t.name, t.user_id, t.input[:2000], t.output[:4000], t.intent,
           round((time.perf_counter() - t.t0) * 1000, 2), t.input_tokens, t.output_tokens, round(t.cost, 6),
           t.llm_calls, json.dumps(t.spans, default=str)[:20000], t.error, _run_id.get(),
           dt.datetime.now(config.TZ).replace(tzinfo=None).isoformat(timespec="seconds"))
    sql = ("INSERT INTO traces(trace_id,name,user_id,input,output,intent,latency_ms,input_tokens,output_tokens,"
           "cost_usd,llm_calls,spans,error,run_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
    if conn is not None:
        conn.execute(sql, row)
    else:
        from .db import session
        with session() as c:
            c.execute(sql, row)


def _mirror_to_opik(t: Trace) -> None:
    """Optional: send the trace to Opik (needs `pip install opik` and `opik configure`)."""
    if not (os.getenv("OPIK_API_KEY") or os.getenv("OPIK_URL_OVERRIDE")):
        return
    try:
        import opik  # type: ignore
        client = opik.Opik(project_name=os.getenv("OPIK_PROJECT_NAME", "netracare"))
        tr = client.trace(name=t.name, input={"text": t.input}, output={"text": t.output},
                          metadata={"intent": t.intent, "cost_usd": t.cost, "tokens": t.input_tokens + t.output_tokens})
        for s in t.spans:
            tr.span(name=s["name"], input=s.get("meta", {}), output={"ms": s.get("ms")})
        tr.end()
    except Exception:
        pass


@contextmanager
def trace(name: str, user_id: int | None = None, input: str = "", conn=None):
    t = Trace(name, user_id, input)
    token = _current.set(t)
    try:
        yield t
    except Exception as exc:
        t.error = str(exc)
        raise
    finally:
        _current.reset(token)
        try:
            _save(t, conn)
            _mirror_to_opik(t)
        except Exception:
            pass  # observability must never break the app
