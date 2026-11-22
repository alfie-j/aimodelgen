"""Step 5: turn the surviving lessons into ShareGPT-style training lines.

Kept = auto-kept items (minus any a reviewer rejected on spot check)
       + queued items a reviewer accepted.
Unreviewed queue items are left out. Anything whose learner message overlaps
the held-out evaluation questions is dropped, so the base-vs-fine-tuned test
is on questions the student has not seen.

    python -m pipeline.build_dataset
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter

from tools.dedup import jaccard, shingles
from tools.materials import ROOT, prompt
from tools.tags import training_target

DATA = ROOT / "outputs" / "data"
HELDOUT = ROOT / "eval" / "heldout.jsonl"


def load(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def to_sharegpt(row: dict, system: str) -> dict:
    return {
        "id": row["gen_id"],
        "skill": row["skill_id"],
        "conversations": [
            {"from": "system", "value": system},
            {"from": "human", "value": row["learner_message"]},
            {"from": "gpt", "value": training_target(row["plan"], row["explanation"])},
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--val-frac", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=1202)
    args = ap.parse_args()

    decisions = {d["gen_id"]: d["decision"] for d in load(DATA / "review_decisions.jsonl")}
    auto = [r for r in load(DATA / "filtered.jsonl") if decisions.get(r["gen_id"]) != "reject"]
    accepted = [r for r in load(DATA / "review_queue.jsonl") if decisions.get(r["gen_id"]) == "accept"]
    rows = auto + accepted

    held = [shingles(h["question"], 4) for h in load(HELDOUT)]
    clean, contaminated = [], 0
    for r in rows:
        s = shingles(r["learner_message"], 4)
        if any(jaccard(s, h) > 0.5 for h in held):
            contaminated += 1
        else:
            clean.append(r)

    system = prompt("student_system.md").strip()
    lines = [to_sharegpt(r, system) for r in clean]
    rng = random.Random(args.seed)
    rng.shuffle(lines)
    n_val = max(1, int(len(lines) * args.val_frac)) if len(lines) > 20 else 0
    val, train = lines[:n_val], lines[n_val:]
    for name, data in (("train.jsonl", train), ("val.jsonl", val)):
        with (DATA / name).open("w") as f:
            for l in data:
                f.write(json.dumps(l, ensure_ascii=False) + "\n")

    card = {
        "format": "ShareGPT-style JSONL (system / human / gpt), gpt turn = <thought>plan</thought> + lesson",
        "teacher": sorted({r["teacher"] for r in rows}),
        "auto_kept": len(auto),
        "accepted_after_review": len(accepted),
        "dropped_for_overlap_with_heldout": contaminated,
        "train": len(train),
        "val": len(val),
        "by_skill": dict(sorted(Counter(l["skill"] for l in lines).items())),
        "reviewed_by_human": len(decisions),
    }
    (DATA / "dataset_card.json").write_text(json.dumps(card, indent=2))
    print(json.dumps(card, indent=2))


if __name__ == "__main__":
    main()
