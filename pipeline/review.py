"""Step 4: the human physics check.

Walks through outputs/data/review_queue.jsonl one item at a time. You see why it
was flagged, the plan and the lesson, and decide. Decisions are appended to
review_decisions.jsonl (so you can stop any time and resume). You can also
spot-check items the filter kept automatically with --spot-check N.

    python -m pipeline.review
    python -m pipeline.review --spot-check 30
"""
from __future__ import annotations

import argparse
import json
import random
import textwrap

from tools.materials import ROOT

DATA = ROOT / "outputs" / "data"
QUEUE = DATA / "review_queue.jsonl"
KEPT = DATA / "filtered.jsonl"
DECISIONS = DATA / "review_decisions.jsonl"


def load(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def decided() -> dict[str, dict]:
    return {d["gen_id"]: d for d in load(DECISIONS)}


def show(row: dict, i: int, n: int) -> None:
    w = lambda s: textwrap.indent(textwrap.fill(s, 100, replace_whitespace=False), "    ")
    f = row.get("filter", {})
    print("\n" + "=" * 104)
    print(f"[{i}/{n}] {row['gen_id']}  {row['skill_id']} {row['kind']}   flagged by: {f.get('gate') or 'spot check'}")
    for note in f.get("notes", []):
        print(f"  ! {note}")
    print(f"\n  LEARNER: {row['learner_message']}")
    print("\n  PLAN:")
    print(w(row.get("plan") or ""))
    print("\n  LESSON:")
    for para in (row.get("explanation") or "").split("\n"):
        print(w(para) if para.strip() else "")
    print("\n  CHECKS:", json.dumps(row.get("checks"))[:600])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spot-check", type=int, default=0, help="also review N random auto-kept items")
    ap.add_argument("--reviewer", default="Alfie")
    args = ap.parse_args()

    done = decided()
    items = [r for r in load(QUEUE) if r["gen_id"] not in done]
    if args.spot_check:
        pool = [r for r in load(KEPT) if r["gen_id"] not in done]
        items += random.Random(7).sample(pool, min(args.spot_check, len(pool)))
    print(f"{len(items)} to review. Keys: a = accept, r = reject, s = skip, q = quit")
    with DECISIONS.open("a", encoding="utf-8") as out:
        for i, row in enumerate(items, 1):
            show(row, i, len(items))
            while True:
                k = input("\n  decision [a/r/s/q]: ").strip().lower()
                if k in {"a", "r", "s", "q"}:
                    break
            if k == "q":
                break
            if k == "s":
                continue
            note = input("  note (optional): ").strip()
            out.write(json.dumps({"gen_id": row["gen_id"], "decision": "accept" if k == "a" else "reject",
                                  "note": note, "reviewer": args.reviewer,
                                  "source": "queue" if row.get("filter", {}).get("verdict") == "review" else "spot_check"}) + "\n")
            out.flush()
    d = decided()
    print(f"\n{sum(x['decision']=='accept' for x in d.values())} accepted, "
          f"{sum(x['decision']=='reject' for x in d.values())} rejected so far.  next: python -m pipeline.build_dataset")


if __name__ == "__main__":
    main()
