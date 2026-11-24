"""Agent Skills loader.

Skills are folders under /skills, each with a SKILL.md (YAML-style frontmatter: name, description).
Only name + description are always loaded; a skill's body is added to the prompt when the patient's
message matches it ("progressive disclosure"). The same folders work as Claude Code / Claude skills:
copy them into `.claude/skills/`.
"""
import re
from functools import lru_cache
from pathlib import Path

from .config import BASE_DIR
from .rag import tokens

SKILLS_DIR = BASE_DIR / "skills"
BASE_SKILL = "clinic-front-desk"


@lru_cache(maxsize=1)
def load_skills() -> dict[str, dict]:
    out = {}
    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        raw = path.read_text(encoding="utf-8")
        m = re.match(r"---\s*\n(.*?)\n---\s*\n(.*)", raw, re.S)
        if not m:
            continue
        meta = dict(re.findall(r"^(\w+):\s*(.+)$", m.group(1), re.M))
        name = meta.get("name", path.parent.name)
        out[name] = {"name": name, "description": meta.get("description", ""), "body": m.group(2).strip(), "path": str(path)}
    return out


def list_skills() -> list[dict]:
    return [{"name": s["name"], "description": s["description"]} for s in load_skills().values()]


def select(text: str, limit: int = 2) -> list[str]:
    """Names of skills relevant to the text (the base skill is always first)."""
    q = set(tokens(text))
    scored = []
    for name, s in load_skills().items():
        if name == BASE_SKILL:
            continue
        overlap = len(q & set(tokens(s["name"].replace("-", " ") + " " + s["description"])))
        if overlap >= 2:
            scored.append((overlap, name))
    chosen = [n for _, n in sorted(scored, reverse=True)[:limit]]
    return ([BASE_SKILL] if BASE_SKILL in load_skills() else []) + chosen


def system_prompt(text: str) -> str:
    skills = load_skills()
    names = select(text)
    return "\n\n" + "\n\n".join(skills[n]["body"] for n in names if n in skills)
