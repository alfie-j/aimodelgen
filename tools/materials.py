"""Loading the topic scope, curriculum and problems, and counting exam weights."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAT = ROOT / "materials"
PROMPTS = ROOT / "prompts"


def topic_scope() -> str:
    return (MAT / "topic_scope.md").read_text(encoding="utf-8")


def curriculum() -> dict:
    return json.loads((MAT / "curriculum.json").read_text(encoding="utf-8"))


def problems() -> list[dict]:
    out: list[dict] = []
    for name in ("problems_ioaa.jsonl", "problems.jsonl"):
        p = MAT / name
        if p.exists():
            out += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return out


def exam_weights() -> dict[str, int]:
    """How many problems use each skill. Counted from the problems, never guessed."""
    c: Counter[str] = Counter()
    for p in problems():
        c.update(p.get("skills", []))
    return {k: c.get(k, 0) for k in sorted(curriculum()["skills"])}


def render_problems() -> str:
    return "\n".join(
        f"[{p['id']}] ({', '.join(p['skills'])}; {p.get('source', '')}) {p['question']}\n    Worked answer: {p['worked_answer']}"
        for p in problems()
    )


def render_weights() -> str:
    names = curriculum()["skills"]
    total = len(problems())
    return "\n".join(f"{k} {names[k]['name']}: used in {n} of {total} problems" for k, n in exam_weights().items())


def prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")
