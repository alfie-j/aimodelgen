"""Persistent memory: the fix for the hallucinated textbook detail.

Two parts are given to the tutor on every turn:
  1. the pinned source: the topic-scope document and the past problems, so the
     tutor quotes them instead of recalling a "textbook" from its weights;
  2. a per-learner memory saved to disk: what they know, which skills are done,
     their misconceptions and quiz results. It survives restarts and long chats,
     so only the last few turns of raw history need to be sent.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

from tools.materials import ROOT, curriculum

STORE = ROOT / "data" / "learners"
SKILLS = list(curriculum()["skills"])
STATUSES = ["not started", "in progress", "taught", "checked"]
_lock = threading.Lock()


def blank_memory() -> dict:
    return {"summary": "New student. Nothing known yet.", "skills": {s: "not started" for s in SKILLS},
            "misconceptions": [], "quiz": [], "next_step": "Diagnose what they already know.", "stage": "Diagnose"}


def new_learner(name: str = "") -> dict:
    lid = uuid.uuid4().hex[:10]
    rec = {"id": lid, "name": name.strip()[:40] or "Learner", "created": time.strftime("%Y-%m-%d %H:%M"),
           "history": [], "memory": blank_memory(), "memory_updates": 0}
    save(rec)
    return rec


def path(lid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{10}", lid):
        raise ValueError("bad learner id")
    return STORE / f"{lid}.json"


def load(lid: str) -> dict:
    return json.loads(path(lid).read_text())


def save(rec: dict) -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    with _lock:
        tmp = path(rec["id"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        tmp.replace(path(rec["id"]))


def render(mem: dict) -> str:
    skills = ", ".join(f"{k}: {v}" for k, v in mem["skills"].items())
    mis = "; ".join(mem["misconceptions"]) or "none noted"
    quiz = "; ".join(f"{q.get('q', '')[:60]} -> {'right' if q.get('correct') else 'wrong'}" for q in mem["quiz"][-6:]) or "none yet"
    return (f"Summary: {mem['summary']}\nSkills: {skills}\nMisconceptions seen: {mis}\n"
            f"Recent quiz answers: {quiz}\nCurrent stage: {mem['stage']}\nPlanned next step: {mem['next_step']}")


UPDATE_PROMPT = """You keep a tutor's notes about one student. Update the notes after the latest exchange.

CURRENT NOTES (JSON):
{memory}

LATEST EXCHANGE
Student: {student}
Tutor: {tutor}

Return the updated notes as JSON only, with exactly these keys:
"summary" (under 60 words: what the student knows and how they learn),
"skills" (an object with keys {skills}; each value one of {statuses}),
"misconceptions" (list of short strings, the student's own mistaken ideas),
"quiz" (list of {{"q": short question, "correct": true/false}} for questions the student has ANSWERED; keep earlier ones),
"next_step" (one short sentence),
"stage" (one of Diagnose, Map, Plan, Teach, Check)."""


def update_prompt(mem: dict, student: str, tutor: str) -> list[dict]:
    return [{"role": "user", "content": UPDATE_PROMPT.format(
        memory=json.dumps({k: v for k, v in mem.items()}, ensure_ascii=False), student=student[:1500],
        tutor=tutor[:2500], skills=", ".join(SKILLS), statuses=", ".join(STATUSES))}]


def merge_update(mem: dict, text: str) -> dict:
    """Accept only well-formed fields; keep the old value for anything malformed."""
    try:
        new = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except (json.JSONDecodeError, ValueError):
        return mem
    out = dict(mem)
    if isinstance(new.get("summary"), str):
        out["summary"] = new["summary"][:400]
    if isinstance(new.get("skills"), dict):
        out["skills"] = {s: (new["skills"].get(s) if new["skills"].get(s) in STATUSES else mem["skills"][s]) for s in SKILLS}
    if isinstance(new.get("misconceptions"), list):
        out["misconceptions"] = [str(m)[:120] for m in new["misconceptions"]][:8]
    if isinstance(new.get("quiz"), list):
        out["quiz"] = [{"q": str(q.get("q", ""))[:120], "correct": bool(q.get("correct"))}
                       for q in new["quiz"] if isinstance(q, dict)][-20:]
    if isinstance(new.get("next_step"), str):
        out["next_step"] = new["next_step"][:200]
    if new.get("stage") in ("Diagnose", "Map", "Plan", "Teach", "Check"):
        out["stage"] = new["stage"]
    return out
