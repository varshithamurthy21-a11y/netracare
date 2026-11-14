"""Daily eye-fact banner. Curated facts always work; an LLM can refresh them daily."""
import datetime as dt

from . import llm
from .db import session

FACTS = [
    ("Your eyes blink about 15–20 times a minute — roughly 15,000 times a day.", "Blink"),
    ("The human eye can distinguish around 10 million different colours.", "Colour"),
    ("The cornea is the only part of the body with no blood supply; it gets oxygen straight from the air.", "Cornea"),
    ("The eye's muscles are among the fastest-reacting muscles in the human body.", "Muscles"),
    ("Newborns can't produce tears for the first few weeks of life.", "Tears"),
    ("Your retina contains over 100 million light-sensing cells.", "Retina"),
    ("The 20-20-20 habit: every 20 minutes, look 20 feet away for 20 seconds to rest your eyes.", "Screens"),
    ("Everyone's iris pattern is unique — even identical twins have different ones.", "Iris"),
    ("Your eyes stay roughly the same size from birth to adulthood, while most of the body grows.", "Size"),
    ("Sunglasses that block UV light help protect the delicate tissues of the eye.", "UV"),
    ("Tears have three layers — oil, water and mucus — that work together to keep the eye surface smooth.", "Tears"),
    ("Both eyes send slightly different images; your brain blends them to give you depth perception.", "Depth"),
    ("Pupils change size not only with light, but also with attention and emotion.", "Pupil"),
    ("About 80% of what we perceive comes through our sense of sight.", "Sight"),
    ("Regular comprehensive eye exams can spot some eye conditions before you notice any symptoms.", "Check-ups"),
]


def _today() -> str:
    return dt.date.today().isoformat()


def fact_of_the_day() -> dict:
    day = dt.date.today()
    text, tag = FACTS[day.toordinal() % len(FACTS)]
    source = "curated"
    if llm.available():
        key = f"fact:{day.isoformat()}"
        with session() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            if row:
                text, source = row["value"], "ai"
            else:
                out = llm.generate(
                    "Write ONE short, fun, accurate fact (max 28 words) about the human eye or vision. "
                    "No medical advice, no instructions, no treatment claims. Output only the fact.",
                    system="You write friendly trivia for an eye clinic's website.", max_tokens=80)
                if out:
                    text, source = out.strip().strip('"'), "ai"
                    conn.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, text))
    return {"fact": text, "tag": tag, "source": source, "date": _today()}
