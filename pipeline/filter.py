"""Step 3: decide which teacher outputs deserve to be copied.

Every generation passes through these gates in order; the first failure is the
recorded reason. Clear failures are rejected; anything a program can't decide
goes to a human review queue (outputs/data/review_queue.jsonl), which the
physics checker works through with `python -m pipeline.review`.

  1 format        one <thought> plan, one <checks> JSON list
  2 length        plan and explanation within sensible bounds
  3 numbers       every claim in <checks> recomputed by tools/physics.py
  4 contradiction the same calculation claimed with two different answers
  5 text physics  "k times farther ... n times fainter" in prose recomputed (to review)
  6 sign          brighter-means-larger-magnitude style statements
  7 invented      coordinate transformations / frames (the topic needs none)
  8 pedagogy      must end with a check-in question for the learner
  9 duplicate     near-duplicate explanations (MinHash + Jaccard)
 10 judge         (optional, --judge) a second model reads for physics errors;
                  anything it flags goes to human review, never auto-kept

    python -m pipeline.filter [--judge]
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

from tools.dedup import find_duplicates
from tools.physics import check_claim
from tools.tags import parse_teacher_output

from tools.materials import ROOT

DATA = ROOT / "outputs" / "data"
RAW = DATA / "raw.jsonl"
KEPT = DATA / "filtered.jsonl"
REJECTED = DATA / "rejected.jsonl"
QUEUE = DATA / "review_queue.jsonl"
REPORT = DATA / "filter_report.json"

GATES = ["format", "length", "numbers", "contradiction", "text_physics", "sign", "invented", "pedagogy", "duplicate", "judge"]

WORDNUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8, "nine": 9, "ten": 10,
           "twenty": 20, "hundred": 100, "a hundred": 100, "one hundred": 100, "sixteen": 16,
           "twenty-five": 25, "four hundred": 400, "nine hundred": 900, "sixty-four": 64}
NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted(WORDNUM, key=len, reverse=True)) + r")"

FARTHER_FAINTER = re.compile(
    NUM + r"\s*(?:times|x|×)\s*(?:as\s+)?(?:farther|further)(?:\s+away)?[^.?!]{0,80}?\b" + NUM +
    r"\s*(?:times|x|×)\s*(?:fainter|dimmer|less\s+(?:bright|light|flux))", re.I)

SIGN_ERRORS = [
    re.compile(r"\b(?:larger|higher|bigger|greater)\s+(?:the\s+)?magnitudes?\b[^.?!]{0,30}\b(?:means?|is|are|=)\s+(?:a\s+)?brighter", re.I),
    re.compile(r"\bbrighter\s+(?:stars?|objects?)\s+(?:has|have)\s+(?:a\s+)?(?:larger|higher|bigger|greater)\s+magnitudes?", re.I),
    re.compile(r"\bfainter\s+(?:stars?|objects?)\s+(?:has|have)\s+(?:a\s+)?(?:smaller|lower|more\s+negative)\s+magnitudes?", re.I),
    re.compile(r"\binversely\s+proportional\s+to\s+(?:the\s+)?distance\b(?!\s*(?:squared|\^?\s*2|²))", re.I),
]
INVENTED = re.compile(
    r"coordinate\s+(?:transformation|transform|change|rotation)|change\s+of\s+(?:basis|frame|coordinates)|"
    r"(?:rotate|rotating)\s+(?:the\s+)?(?:axes|coordinate)|reference\s+frame|lorentz|galilean\s+transform", re.I)
LY_IN_MODULUS = re.compile(r"5\s*\\?log[^.\n]{0,40}(?:light[- ]years?|\bly\b)", re.I)


def _num(s: str) -> float:
    s = s.lower().strip()
    return float(WORDNUM[s]) if s in WORDNUM else float(s)


HEDGE = re.compile(r"\b(?:think|thinks|thought|guess|guesses|might|may|seems?|assume|expect|believe|not|isn't|doesn't|"
                   r"wrong|mistake|myth|instead|rather|tempting|intuition|naive|common|actually|but)\b", re.I)


def _sentence(text: str, start: int, end: int) -> str:
    a = max(text.rfind(c, 0, start) for c in ".?!\n") + 1
    b = min([i for i in (text.find(c, end) for c in ".?!\n") if i >= 0] or [len(text)])
    return text[a:b + 1]


def text_physics(expl: str) -> list[str]:
    """Prose claims like '10 times farther ... 100 times fainter', recomputed.

    A sentence that quotes the misconception ("you might think ... 10 times
    fainter, but ...") is the lesson doing its job, so hedged sentences are skipped.
    """
    errs = []
    for m in FARTHER_FAINTER.finditer(expl):
        k, n = _num(m.group(1)), _num(m.group(2))
        if math.isclose(n, k * k, rel_tol=0.02):
            continue
        if HEDGE.search(_sentence(expl, m.start(), m.end())):
            continue
        errs.append(f"'{m.group(0)[:80]}': {k:g}x farther should be {k*k:g}x fainter")
    return errs


def sign_issues(expl: str) -> list[str]:
    out = [f"'{m.group(0)[:80]}'" for rx in SIGN_ERRORS for m in rx.finditer(expl)]
    out += [f"light-years in the distance modulus: '{m.group(0)[:60]}'" for m in LY_IN_MODULUS.finditer(expl)]
    return out


def contradictions(checks: list[dict]) -> list[str]:
    seen: dict[tuple, tuple] = {}
    out = []
    outputs = {"flux_ratio", "delta_mag", "mu", "d_pc", "M", "m", "m_total", "L1_over_L2", "value"}
    for c in checks:
        try:
            inputs = tuple(sorted((k, json.dumps(v)) for k, v in c.items() if k not in outputs))
            result = tuple(sorted((k, float(v)) for k, v in c.items() if k in outputs and not isinstance(v, (list, dict))))
        except (TypeError, ValueError):
            continue
        if inputs in seen and seen[inputs] != result:
            out.append(f"{c.get('type')}: same inputs, answers {seen[inputs]} vs {result}")
        seen.setdefault(inputs, result)
    return out


def gate(row: dict) -> tuple[str, str, list[str]]:
    """Return (verdict, gate, notes). verdict is keep / reject / review."""
    p = parse_teacher_output(row["text"])
    row["plan"], row["explanation"], row["checks"] = p.plan, p.explanation, p.checks
    if p.problems or p.plan is None or p.checks is None:
        return "reject", "format", p.problems
    pw, ew = len(p.plan.split()), len(p.explanation.split())
    if not (15 <= pw <= 260) or not (60 <= ew <= 650):
        return "reject", "length", [f"plan {pw} words, explanation {ew} words"]
    bad = []
    for c in p.checks:
        r = check_claim(c)
        if not r.ok:
            bad.append(f"{r.kind}: claimed {r.claimed}, expected {r.expected} {r.detail}".strip())
    if bad:
        return "reject", "numbers", bad
    c = contradictions(p.checks)
    if c:
        return "reject", "contradiction", c
    t = text_physics(p.explanation)  # plans name the misconception on purpose, so they aren't checked
    if t:
        return "review", "text_physics", t
    s = sign_issues(p.explanation)
    if s:
        return "review", "sign", s  # regexes can misfire on "a larger magnitude means brighter? No!"
    inv = INVENTED.findall(p.explanation)
    if inv:
        return "reject", "invented", [f"mentions: {', '.join(sorted(set(i.lower() for i in inv)))}"]
    tail = p.explanation.strip()[-400:]
    if "?" not in tail:
        return "reject", "pedagogy", ["no check-in question at the end"]
    if row.get("kind") == "problem" and not p.checks:
        return "review", "numbers", ["worked problem but no numerical claims listed"]
    return "keep", "", []


JUDGE_PROMPT = """You are checking a beginner astronomy lesson for physics errors before it is used as training data.
Conventions: log is base 10, distances in parsecs, brighter means SMALLER magnitude, F = L/(4 pi d^2), m2 - m1 = -2.5 log(F2/F1), m - M = 5 log(d/10 pc) + A.

LESSON PLAN:
{plan}

LESSON:
{explanation}

Answer with JSON only:
{{"physics_correct": true/false, "errors": ["..."], "self_contradiction": true/false, "invented_method": true/false, "beginner_followable": 1-5}}"""


def judge(rows: list[dict], model_key: str) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from tools.llm import LLM

    llm = LLM(model_key)

    def one(row: dict) -> None:
        try:
            r = llm.chat([{"role": "user", "content": JUDGE_PROMPT.format(plan=row["plan"], explanation=row["explanation"])}],
                         temperature=0, max_tokens=400, tag="judge")
            txt = re.sub(r"^```(?:json)?|```$", "", r.text.strip()).strip()
            row["judge"] = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        except Exception as e:
            row["judge"] = {"error": str(e)[:200]}

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(one, rows))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", action="store_true", help="also run the judge model over survivors")
    ap.add_argument("--judge-model", default=None)
    ap.add_argument("--dup-threshold", type=float, default=0.7)
    args = ap.parse_args()

    rows = [json.loads(l) for l in RAW.read_text(encoding="utf-8").splitlines() if l.strip()]
    counts = Counter()
    kept, rejected, queue = [], [], []
    for row in rows:
        verdict, g, notes = gate(row)
        row["filter"] = {"verdict": verdict, "gate": g, "notes": notes}
        {"keep": kept, "reject": rejected, "review": queue}[verdict].append(row)
        if verdict != "keep":
            counts[(verdict, g)] += 1

    # duplicates among everything that survived or awaits review
    pool = kept + queue
    dups = find_duplicates([r["explanation"] for r in pool], threshold=args.dup_threshold)
    survivors_k, survivors_q = [], []
    for i, r in enumerate(pool):
        if i in dups:
            r["filter"] = {"verdict": "reject", "gate": "duplicate", "notes": [f"near-copy of {pool[dups[i]]['gen_id']}"]}
            rejected.append(r)
            counts[("reject", "duplicate")] += 1
        else:
            (survivors_k if r["filter"]["verdict"] == "keep" else survivors_q).append(r)
    kept, queue = survivors_k, survivors_q

    if args.judge and kept:
        from tools.llm import load_config

        judge(kept, args.judge_model or load_config()["roles"]["judge"])
        still = []
        for r in kept:
            j = r.get("judge", {})
            if j.get("error"):
                still.append(r)
            elif not j.get("physics_correct", True) or j.get("self_contradiction") or j.get("invented_method"):
                r["filter"] = {"verdict": "review", "gate": "judge", "notes": j.get("errors", []) or ["judge flagged"]}
                queue.append(r)
                counts[("review", "judge")] += 1
            else:
                still.append(r)
        kept = still

    for path, data in ((KEPT, kept), (REJECTED, rejected), (QUEUE, queue)):
        with path.open("w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r) + "\n")

    report = {
        "generated": len(rows),
        "kept_automatically": len(kept),
        "rejected": len(rejected),
        "awaiting_review": len(queue),
        "by_gate": {g: {"rejected": counts[("reject", g)], "to_review": counts[("review", g)]} for g in GATES},
        "by_skill_kept": dict(Counter(r["skill_id"] for r in kept)),
        "judge_used": bool(args.judge),
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nnext: python -m pipeline.review   ({len(queue)} items need a physics decision)")


if __name__ == "__main__":
    main()
