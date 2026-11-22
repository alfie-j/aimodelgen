"""Comparison kit, step 3: un-blind the ratings and summarise per model and condition.

    python summarise.py                      # uses outputs/compare/blind/rating_sheet.csv
Prints a table and writes outputs/compare/summary.json. Unrated rows are ignored.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict

from make_blind import CRITERIA
from tools.materials import ROOT

D = ROOT / "outputs" / "compare"


def main() -> None:
    key = json.loads((D / "blind" / "key.json").read_text())
    raw = {(r["model"], r["condition"], r["prompt_id"]): r for r in map(json.loads, (D / "raw.jsonl").read_text().splitlines())}
    groups: dict[tuple, dict] = defaultdict(lambda: {c: [] for c in CRITERIA} | {"cost": [], "words": [], "n": 0})
    with (D / "blind" / "rating_sheet.csv").open() as f:
        for row in csv.DictReader(f):
            k = key.get(row["code"])
            if not k:
                continue
            vals = {c: row.get(c, "").strip() for c in CRITERIA}
            if not any(vals.values()):
                continue
            g = groups[(k["model"], k["condition"])]
            g["n"] += 1
            for c, v in vals.items():
                if v:
                    g[c].append(float(v))
            r = raw.get((k["model"], k["condition"], k["prompt_id"]))
            if r:
                g["cost"].append(r["cost_usd"])
                g["words"].append(len(r["text"].split()))
    mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    out = []
    for (m, c), g in sorted(groups.items()):
        out.append({"model": m, "condition": c, "rated": g["n"], **{k: mean(g[k]) for k in CRITERIA},
                    "mean_words": mean(g["words"]), "total_cost_usd": round(sum(g["cost"]), 4)})
    (D / "summary.json").write_text(json.dumps(out, indent=2))
    cols = ["model", "condition", "rated", *CRITERIA, "mean_words", "total_cost_usd"]
    print(" | ".join(cols))
    for r in out:
        print(" | ".join(str(r[c]) for c in cols))
    print("\nOur judgment on our own prompts; not a general ranking of these models.")


if __name__ == "__main__":
    main()
