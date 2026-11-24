"""Retrieval-augmented answers over the NetraCare knowledge base.

Hybrid search = two retrievers fused with Reciprocal Rank Fusion (RRF):
  * BM25 over word tokens  — exact/keyword matching ("cataract", "UPI")
  * TF-IDF cosine over character 3-grams — tolerant to typos and word forms ("cataracts", "cancelation")
Chunks come from the markdown files in backend/knowledge/ plus live doctor profiles from the database,
so answers stay correct when an admin adds or pauses a doctor. Every answer carries numbered citations.
"""
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from . import llm, observability

KB_DIR = Path(__file__).parent / "knowledge"
STOP = set("""a an and are as at be but by can could do does for from had has have how i if in into is it its me my of on or our
so than that the their them then there these they this to up us was we were what when where which who why will with would you your
please tell about get take give want need know make let like also just any some very really really""".split())

SYNONYMS = {
    "cost": "price fee rupees", "price": "cost fee rupees", "fee": "price cost rupees", "charge": "price fee rupees",
    "much": "price cost fee", "expensive": "price cost", "pay": "payment cash upi card", "upi": "payment", "card": "payment insurance",
    "hours": "open session", "open": "hours session", "timing": "hours open session", "timings": "hours open session",
    "cancel": "cancelling rescheduling release", "cancellation": "cancelling", "reschedule": "rescheduling cancelling",
    "kid": "child children paediatric", "kids": "child children paediatric", "child": "children paediatric pediatric",
    "baby": "child children paediatric", "address": "location", "where": "location", "phone": "contact", "call": "contact phone",
    "wait": "queue waiting", "appointment": "visit", "bring": "carry documents", "late": "arrival", "insurance": "cashless", "refund": "payment",
}


DOC_HINTS = {  # tiny prior: some words strongly suggest which document answers the question
    "costs": {"cost", "price", "fee", "fees", "much", "charge", "rupees", "expensive", "insurance", "cashless", "bill", "receipt"},
    "policies": {"cancel", "cancellation", "reschedule", "late", "policy", "policies", "refund", "noshow", "privacy", "summary", "summaries"},
    "clinic_info": {"hours", "open", "closed", "parking", "address", "location", "phone", "bring", "upi", "cash", "languages", "wheelchair"},
}


def expand(query: str) -> str:
    words = re.findall(r"[a-z0-9]+", query.lower())
    extra = [SYNONYMS[w] for w in words if w in SYNONYMS]
    return query + " " + " ".join(extra)


def stem(w: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)] + ("y" if suf == "ies" else "")
            break
    if len(w) > 4 and w.endswith("e"):  # reschedule / rescheduling -> reschedul
        w = w[:-1]
    if len(w) > 5 and w[-1] == w[-2]:  # cancell -> cancel
        w = w[:-1]
    return w


def tokens(text: str, keep_stop: bool = False) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if keep_stop or w not in STOP]


def ngrams(text: str, n: int = 3) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOP:
            continue
        w = f" {w} "
        out += [w[i:i + n] for i in range(max(1, len(w) - n + 1))]
    return out


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


# ---------------------------------------------------------------- chunks
def load_static_chunks() -> list[dict]:
    chunks = []
    for path in sorted(KB_DIR.glob("*.md")):
        title, heading, buf = path.stem, "", []

        def flush():
            body = " ".join(buf).strip()
            if body:
                chunks.append({"id": f"{path.stem}#{slug(heading)}", "doc": path.stem, "title": title, "heading": heading, "text": body})
            buf.clear()

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
            elif line.startswith("## "):
                flush()
                heading = line[3:].strip()
            elif line.strip():
                buf.append(line.strip())
        flush()
    return chunks


def doctor_chunks(doctors: list[dict]) -> list[dict]:
    out = []
    for d in doctors:
        text = (f"{d['name']} is a {d['specialty']} specialist with {d['years']} years of experience, seeing patients in {d['room']}. "
                f"Areas of focus: {d['focus']}. Languages spoken: {d['languages']}. {d['bio']}")
        out.append({"id": f"doctor#{slug(d['name'])}", "doc": "doctors", "title": "NetraCare Doctors", "heading": d["name"], "text": text})
    return out


# ---------------------------------------------------------------- index
class Index:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        # leg 1: BM25 over word tokens (heading counted double)
        self.docs = [tokens(c["heading"] + " " + c["heading"] + " " + c["title"] + " " + c["text"]) for c in chunks]
        self.n = len(chunks)
        self.avgdl = sum(len(d) for d in self.docs) / max(1, self.n)
        df = Counter(t for d in self.docs for t in set(d))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]
        # leg 2: TF-IDF over character 3-grams
        grams = [Counter(ngrams(c["heading"] + " " + c["text"])) for c in chunks]
        gdf = Counter(g for c in grams for g in c)
        self.gidf = {g: math.log((1 + self.n) / (1 + f)) + 1 for g, f in gdf.items()}
        self.gvec = []
        for c in grams:
            v = {g: (1 + math.log(f)) * self.gidf[g] for g, f in c.items()}
            norm = math.sqrt(sum(x * x for x in v.values())) or 1
            self.gvec.append({g: x / norm for g, x in v.items()})

    def bm25(self, q_tokens: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
        scores = []
        for i, tf in enumerate(self.tf):
            dl, s = len(self.docs[i]), 0.0
            for t in q_tokens:
                if t in tf:
                    s += self.idf.get(t, 0) * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / self.avgdl))
            scores.append(s)
        return scores

    def ngram_cos(self, query: str) -> list[float]:
        q = Counter(ngrams(query))
        v = {g: (1 + math.log(f)) * self.gidf.get(g, 0) for g, f in q.items() if g in self.gidf}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1
        v = {g: x / norm for g, x in v.items()}
        return [sum(w * dv.get(g, 0) for g, w in v.items()) for dv in self.gvec]

    def search(self, query: str, k: int = 4) -> list[dict]:
        q_tokens = tokens(query)
        if not q_tokens:
            return []
        b, g = self.bm25(tokens(expand(query))), self.ngram_cos(query)
        rank_b = {i: r for r, i in enumerate(sorted(range(self.n), key=lambda i: -b[i]), 1) if b[i] > 0}
        rank_g = {i: r for r, i in enumerate(sorted(range(self.n), key=lambda i: -g[i]), 1) if g[i] > 0}
        fused = {i: 1 / (60 + rank_b[i]) if i in rank_b else 0 for i in range(self.n)}
        for i, r in rank_g.items():
            fused[i] += 1 / (60 + r)
        words = set(re.findall(r"[a-z]+", query.lower()))
        for i, c in enumerate(self.chunks):
            if fused[i] > 0 and words & DOC_HINTS.get(c["doc"], set()):
                fused[i] += 0.006
        best = sorted((i for i in fused if fused[i] > 0), key=lambda i: -fused[i])[:k]
        qset = set(q_tokens)
        alt = {stem(w): set(tokens(SYNONYMS[w])) for w in re.findall(r"[a-z0-9]+", query.lower()) if w in SYNONYMS}
        hits = []
        for i in best:
            tset = set(self.docs[i])
            hits.append({**self.chunks[i], "score": round(fused[i], 5), "bm25": round(b[i], 3), "ngram": round(g[i], 3),
                         "coverage": round(sum(1 for t in qset if t in tset or alt.get(t, set()) & tset) / len(qset), 2)})
        return hits


@lru_cache(maxsize=4)
def _cached_index(doctor_sig: tuple) -> Index:
    return Index(load_static_chunks() + doctor_chunks([dict(zip(("name", "specialty", "years", "room", "focus", "languages", "bio"), s)) for s in doctor_sig]))


def get_index(conn=None) -> Index:
    sig: tuple = ()
    if conn is not None:
        from . import services
        sig = tuple((d["name"], d["specialty"], d["years"], d["room"], d["focus"], d["languages"], d["bio"])
                    for d in services.list_doctors(conn))
    return _cached_index(sig)


# ---------------------------------------------------------------- answering
MIN_COVERAGE, MIN_NGRAM = 0.5, 0.35


def is_relevant(hit: dict) -> bool:
    return hit["coverage"] >= MIN_COVERAGE or hit["ngram"] >= MIN_NGRAM


def _extractive(question: str, hits: list[dict]) -> tuple[str, list[int]]:
    """Pick the most relevant sentences: up to 2 from the best chunk, plus 1 strong match from another chunk."""
    q = set(tokens(question))
    chosen: list[tuple[int, int, str]] = []  # (chunk number, position, sentence)
    top = [(len(q & set(tokens(s))), pos, s) for pos, s in enumerate(sentences(hits[0]["text"]))]
    for ov, pos, s in sorted(top, key=lambda x: (-x[0], x[1]))[:2]:
        if ov > 0 or not chosen:
            chosen.append((1, pos, s))
    need = max(2, math.ceil(0.6 * len(q)))
    extra = []
    for ci, h in enumerate(hits[1:3], 2):
        for pos, s in enumerate(sentences(h["text"])):
            ov = len(q & set(tokens(s)))
            if ov >= need:
                extra.append((ov, ci, pos, s))
    for ov, ci, pos, s in sorted(extra, key=lambda x: -x[0])[:1]:
        chosen.append((ci, pos, s))
    chosen.sort(key=lambda x: (x[0], x[1]))
    used = sorted({c for c, _, _ in chosen})
    return " ".join(f"{s} [{c}]" for c, _, s in chosen), used


def answer(question: str, conn=None, system_extra: str = "", k: int = 4) -> dict:
    """Return {answer, citations, grounded, hits}. Never answers from outside the knowledge base."""
    index = get_index(conn)
    with observability.span("retrieve", query=question) as sp:
        hits = index.search(question, k=k)
        sp["top"] = [h["id"] for h in hits]
    if not hits or not is_relevant(hits[0]):
        return {"answer": "I couldn't find that in NetraCare's information. The front desk can help: +91 80 4000 1234 "
                          "(Mon–Sat, 9:00–13:00 and 14:30–18:00).", "citations": [], "grounded": False, "hits": hits}
    context = "\n\n".join(f"[{i}] ({h['title']} — {h['heading']}) {h['text']}" for i, h in enumerate(hits, 1))
    generated = None
    with observability.span("generate", mode="llm" if llm.available() else "extractive"):
        if llm.available():
            generated = llm.generate(
                f"Context passages:\n{context}\n\nQuestion: {question}\n\nAnswer in at most 4 sentences using ONLY the passages. "
                "Cite passages like [1] or [2]. If the passages don't contain the answer, say you don't have that information "
                "and suggest calling the front desk. Never give medical advice.",
                system="You are NetraCare's front-desk assistant. You answer questions about the clinic only." + system_extra,
                max_tokens=350)
    if generated:
        used = sorted({int(n) for n in re.findall(r"\[(\d)\]", generated) if 1 <= int(n) <= len(hits)}) or [1]
        text = generated
    else:
        text, used = _extractive(question, hits)
        if hits[0]["doc"] == "faq" and used[0] == 1:
            text = f"{hits[0]['heading']} {text}"
    cites = [{"n": n, "title": hits[n - 1]["title"], "heading": hits[n - 1]["heading"], "id": hits[n - 1]["id"],
              "snippet": hits[n - 1]["text"][:220]} for n in used]
    return {"answer": text, "citations": cites, "grounded": True, "hits": hits}
