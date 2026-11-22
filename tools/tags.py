"""Parsing the three-part teacher output: <thought> plan, explanation, <checks> JSON."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

THOUGHT_RE = re.compile(r"<thought>(.*?)</thought>", re.S | re.I)
CHECKS_RE = re.compile(r"<checks>(.*?)</checks>", re.S | re.I)
STAGE_RE = re.compile(r"^\s*\[Stage:\s*(Diagnose|Map|Plan|Teach|Check)\s*\]\s*", re.I)
STAGES = ["Diagnose", "Map", "Plan", "Teach", "Check"]


@dataclass
class Parsed:
    plan: str | None
    explanation: str
    checks: list[dict[str, Any]] | None
    problems: list[str] = field(default_factory=list)


def parse_teacher_output(text: str) -> Parsed:
    problems: list[str] = []
    thoughts = THOUGHT_RE.findall(text)
    if len(thoughts) != 1:
        problems.append(f"expected 1 <thought> block, found {len(thoughts)}")
    plan = thoughts[0].strip() if thoughts else None

    checks: list[dict[str, Any]] | None = None
    cm = CHECKS_RE.findall(text)
    if len(cm) != 1:
        problems.append(f"expected 1 <checks> block, found {len(cm)}")
    else:
        raw = cm[0].strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip()
        try:
            val = json.loads(raw)
            if not isinstance(val, list) or not all(isinstance(c, dict) for c in val):
                problems.append("<checks> is not a JSON list of objects")
            else:
                checks = val
        except json.JSONDecodeError as e:
            problems.append(f"<checks> is not valid JSON: {e.msg}")

    body = THOUGHT_RE.sub("", text)
    body = CHECKS_RE.sub("", body)
    body = re.sub(r"(?im)^\s*(PART\s*[123][.:]?.*|\*\*PART\s*[123].*?\*\*)\s*$", "", body)
    explanation = body.strip()
    return Parsed(plan, explanation, checks, problems)


def split_stage(text: str) -> tuple[str | None, str]:
    m = STAGE_RE.match(text)
    if not m:
        return None, text
    return m.group(1).capitalize(), text[m.end():]


def training_target(plan: str, explanation: str) -> str:
    """What the student model learns to write: the plan in thought tags, then the lesson."""
    return f"<thought>\n{plan.strip()}\n</thought>\n\n{explanation.strip()}"
