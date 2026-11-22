"""Step 7: does the fine-tuned student teach better than the base model?

The films said this comparison was never done. This is it. Both systems get the
same student system prompt and the same held-out questions (never trained on),
with greedy decoding so the run is reproducible.

Measured for each answer
  * correct        final numeric answer within tolerance of tools/physics.py
  * has_plan       wrote a <thought> plan
  * check_in       ends with a question to the learner
  * words          length of the lesson
  * judge scores   (optional) a blind judge sees the two lessons as A and B in
                   random order and scores physics, followability, picture-first
                   and check-in, then picks a preference

    python -m eval.run_eval --backend hf                    # one 24 GB GPU, adapter on/off
    python -m eval.run_eval --backend api --a qwen-base --b teachbot   # vLLM server
    python -m eval.run_eval --backend hf --judge            # + blind judge
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import time
from pathlib import Path

from tools.materials import ROOT, prompt
from tools.tags import THOUGHT_RE

HELDOUT = ROOT / "eval" / "heldout.jsonl"
OUT = ROOT / "outputs" / "eval"
ASK_FINAL = "\n\n(At the very end, after your check-in question, write one line: 'Final answer: <number>'.)"


# --------------------------------------------------------------------------- #
# grading
# --------------------------------------------------------------------------- #
NUM_RE = r"[-−]?\d[\d,]*(?:\.\d+)?(?:\s*(?:[eE][-−]?\d+|[×x\*]\s*10\s*\^?\s*\{?[-−]?\d+\}?))?"


def parse_number(s: str) -> float | None:
    s = s.replace("−", "-").replace("$", "").replace("\\times", "×").replace("\\approx", "").replace("≈", "")
    frac = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", s)
    m = re.search(NUM_RE, s)
    if frac and (not m or frac.start() <= m.start()):
        return float(frac.group(1)) / float(frac.group(2))
    if not m:
        return None
    t = m.group(0).replace(",", "").replace(" ", "")
    sci = re.match(r"([-\d.]+)[×x\*]10\^?\{?([-\d]+)\}?", t)
    if sci:
        return float(sci.group(1)) * 10 ** int(sci.group(2))
    try:
        return float(t)
    except ValueError:
        return None


def final_answer(text: str) -> float | None:
    hits = re.findall(r"final\s+answer\s*[:=]\s*\**\s*([^\n]+)", text, re.I)
    return parse_number(hits[-1]) if hits else None


def is_correct(kind: str, expected: float, got: float | None) -> bool:
    if got is None:
        return False
    if kind == "mag":
        return abs(got - expected) <= 0.06
    if kind == "ratio" and expected < 1 and got > 1:  # "1/9 as bright" given as "9 times dimmer"
        got = 1 / got
    return math.isclose(got, expected, rel_tol=0.03)


def lesson_features(text: str) -> dict:
    body = THOUGHT_RE.sub("", text)
    body = re.split(r"(?im)^\s*final\s+answer", body)[0].strip()
    return {"has_plan": bool(THOUGHT_RE.search(text)), "check_in": "?" in body[-300:], "words": len(body.split())}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact p-value for paired correct/incorrect disagreements."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2**n
    return min(1.0, 2 * p)


# --------------------------------------------------------------------------- #
JUDGE = """Two tutors answered the same beginner's astronomy question. Judge them as TEACHERS for someone who has never taken physics.
Conventions: brighter = smaller magnitude; F = L/(4 pi d^2); m2 - m1 = -2.5 log(F2/F1); m - M = 5 log(d/10 pc) + A.

QUESTION: {q}
CORRECT FINAL ANSWER: {ans}

=== TUTOR A ===
{a}

=== TUTOR B ===
{b}

Score each tutor 1-5 on: physics (correct, no invented steps), followable (a beginner could follow it), picture_first (starts from an intuitive picture before maths), check_in (asks the learner a useful question).
Reply with JSON only: {{"A": {{"physics": n, "followable": n, "picture_first": n, "check_in": n}}, "B": {{...}}, "prefer": "A" or "B" or "tie", "why": "one sentence"}}"""


def judge_pairs(rows: list[dict], model_key: str, seed: int = 11) -> None:
    from tools.llm import LLM

    llm = LLM(model_key)
    rng = random.Random(seed)
    for r in rows:
        flip = rng.random() < 0.5
        first, second = ("b", "a") if flip else ("a", "b")
        txt = JUDGE.format(q=r["question"], ans=r["answer"], a=r[first]["text"], b=r[second]["text"])
        try:
            out = llm.chat([{"role": "user", "content": txt}], temperature=0, max_tokens=500, tag="eval-judge").text
            j = json.loads(out[out.find("{"): out.rfind("}") + 1])
            unblind = {"A": first, "B": second}
            r[first]["judge"], r[second]["judge"] = j["A"], j["B"]
            r["prefer"] = unblind.get(j.get("prefer"), "tie")
            r["judge_why"] = j.get("why", "")
            r["judge_order"] = f"A={first},B={second}"
        except Exception as e:
            r["judge_error"] = str(e)[:200]


def summarise(rows: list[dict], names: dict) -> dict:
    n = len(rows)
    rep: dict = {"n_questions": n, "systems": names}
    for s in ("a", "b"):
        k = sum(r[s]["correct"] for r in rows)
        rep[s] = {
            "correct": k, "accuracy": round(k / n, 3) if n else 0, "accuracy_95ci": wilson(k, n),
            "has_plan": sum(r[s]["has_plan"] for r in rows), "check_in": sum(r[s]["check_in"] for r in rows),
            "mean_words": round(sum(r[s]["words"] for r in rows) / max(1, n), 1),
            "no_final_answer": sum(r[s]["got"] is None for r in rows),
        }
        judged = [r[s]["judge"] for r in rows if "judge" in r[s]]
        if judged:
            rep[s]["judge_means"] = {c: round(sum(j[c] for j in judged) / len(judged), 2)
                                     for c in ("physics", "followable", "picture_first", "check_in")}
    b = sum(r["a"]["correct"] and not r["b"]["correct"] for r in rows)
    c = sum(r["b"]["correct"] and not r["a"]["correct"] for r in rows)
    rep["paired"] = {"only_a_correct": b, "only_b_correct": c, "mcnemar_exact_p": round(mcnemar_exact(b, c), 4)}
    prefs = [r.get("prefer") for r in rows if r.get("prefer")]
    if prefs:
        rep["judge_preference"] = {k: prefs.count(k) for k in ("a", "b", "tie")}
    rep["by_skill"] = {}
    for sk in sorted({r["skill"] for r in rows}):
        rs = [r for r in rows if r["skill"] == sk]
        rep["by_skill"][sk] = {"n": len(rs), "a_correct": sum(r["a"]["correct"] for r in rs), "b_correct": sum(r["b"]["correct"] for r in rs)}
    return rep


def write_markdown(rep: dict, path: Path) -> None:
    A, B = rep["systems"]["a"], rep["systems"]["b"]
    L = [f"# Base vs fine-tuned: held-out evaluation", "",
         f"{rep['n_questions']} questions the student never trained on. Greedy decoding. Generated {rep.get('finished', '')}.", "",
         f"| | {A} | {B} |", "|---|---|---|",
         f"| Correct final answer | {rep['a']['correct']}/{rep['n_questions']} ({rep['a']['accuracy']:.0%}, 95% CI {rep['a']['accuracy_95ci'][0]:.0%}–{rep['a']['accuracy_95ci'][1]:.0%}) | {rep['b']['correct']}/{rep['n_questions']} ({rep['b']['accuracy']:.0%}, 95% CI {rep['b']['accuracy_95ci'][0]:.0%}–{rep['b']['accuracy_95ci'][1]:.0%}) |",
         f"| Wrote a teaching plan | {rep['a']['has_plan']} | {rep['b']['has_plan']} |",
         f"| Ended with a check-in question | {rep['a']['check_in']} | {rep['b']['check_in']} |",
         f"| Mean lesson length (words) | {rep['a']['mean_words']} | {rep['b']['mean_words']} |",
         f"| No parseable final answer | {rep['a']['no_final_answer']} | {rep['b']['no_final_answer']} |"]
    if "judge_means" in rep["a"] and "judge_means" in rep["b"]:
        for c in ("physics", "followable", "picture_first", "check_in"):
            L.append(f"| Judge: {c} (1–5) | {rep['a']['judge_means'][c]} | {rep['b']['judge_means'][c]} |")
    p = rep["paired"]
    L += ["", f"Paired: only {A} correct on {p['only_a_correct']}, only {B} correct on {p['only_b_correct']} "
              f"(exact McNemar p = {p['mcnemar_exact_p']}).", ""]
    if "judge_preference" in rep:
        jp = rep["judge_preference"]
        L.append(f"Blind judge preferred {A} {jp['a']}×, {B} {jp['b']}×, tie {jp['tie']}× (order randomised per question).")
    L += ["", "Limits: one held-out set of templated questions; an automatic judge is not a learner; "
              "this measures answers, not learning gains in people."]
    path.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["hf", "api"], default="hf")
    ap.add_argument("--a", default="qwen-base", help="api backend: model key for system A")
    ap.add_argument("--b", default="teachbot", help="api backend: model key for system B")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--judge-model", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-new-tokens", type=int, default=900)
    args = ap.parse_args()

    qs = [json.loads(l) for l in HELDOUT.read_text().splitlines() if l.strip()]
    if args.limit:
        qs = qs[: args.limit]
    system = prompt("student_system.md").strip()

    if args.backend == "hf":
        from tools.student import HFStudent

        st = HFStudent()
        names = {"a": "Base Qwen2.5-14B", "b": "Teach Bot (fine-tuned)"}
        gen = {"a": lambda m: st.generate(m, adapter=False, max_new_tokens=args.max_new_tokens),
               "b": lambda m: st.generate(m, adapter=True, max_new_tokens=args.max_new_tokens)}
    else:
        from tools.student import APIStudent

        sa, sb = APIStudent(args.a), APIStudent(args.b)
        names = {"a": args.a, "b": args.b}
        gen = {"a": lambda m: sa.generate(m, max_new_tokens=args.max_new_tokens),
               "b": lambda m: sb.generate(m, max_new_tokens=args.max_new_tokens)}

    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, q in enumerate(qs, 1):
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": q["question"] + ASK_FINAL}]
        row = {**q}
        for s in ("a", "b"):
            t0 = time.time()
            text = gen[s](msgs)
            got = final_answer(text)
            row[s] = {"text": text, "got": got, "correct": is_correct(q["kind"], q["answer"], got),
                      "seconds": round(time.time() - t0, 1), **lesson_features(text)}
        rows.append(row)
        print(f"[{i}/{len(qs)}] {q['id']} expected {q['answer']:.4g}  A={row['a']['got']} {'✓' if row['a']['correct'] else '✗'}  "
              f"B={row['b']['got']} {'✓' if row['b']['correct'] else '✗'}")

    if args.judge:
        from tools.llm import load_config

        judge_pairs(rows, args.judge_model or load_config()["roles"]["judge"])

    rep = summarise(rows, names)
    rep["finished"] = time.strftime("%Y-%m-%d %H:%M")
    (OUT / "answers.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (OUT / "report.json").write_text(json.dumps(rep, indent=2))
    write_markdown(rep, OUT / "report.md")
    print((OUT / "report.md").read_text())


if __name__ == "__main__":
    main()
