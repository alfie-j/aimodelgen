"""Comparison kit, step 2: hide which model wrote what, so outputs are judged as teaching.

Writes outputs/compare/blind/
  read.html          every answer under a random code, grouped by prompt, shuffled
  rating_sheet.csv   one row per answer: fill in the 1-5 columns
  key.json           code -> model + condition (don't open until rating is done)
"""
from __future__ import annotations

import csv
import html
import json
import random
import string

from tools.materials import ROOT

D = ROOT / "outputs" / "compare"
B = D / "blind"
CRITERIA = ["physics_right", "assumes_little", "beginner_can_follow", "picture_first", "checks_understanding"]


def main(seed: int = 2026) -> None:
    rows = [json.loads(l) for l in (D / "raw.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rng = random.Random(seed)
    codes = set()
    key = {}
    for r in rows:
        while True:
            c = "".join(rng.choices(string.ascii_uppercase, k=3))
            if c not in codes:
                codes.add(c)
                break
        r["code"] = c
        key[c] = {"model": r["model"], "condition": r["condition"], "prompt_id": r["prompt_id"]}
    B.mkdir(parents=True, exist_ok=True)
    (B / "key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    rng.shuffle(rows)
    rows.sort(key=lambda r: r["prompt_id"])  # stable: shuffled within each prompt

    with (B / "rating_sheet.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "prompt_id", *CRITERIA, "notes"])
        for r in rows:
            w.writerow([r["code"], r["prompt_id"], *[""] * len(CRITERIA), ""])

    parts = ["<!doctype html><meta charset=utf-8><title>Blind comparison</title>",
             "<style>body{font:16px/1.55 Georgia,serif;max-width:820px;margin:2rem auto;padding:0 16px;background:#faf6ec;color:#1d1b3a}"
             "h2{border-top:2px solid #1d1b3a;padding-top:1rem}article{background:#fff;padding:1rem 1.2rem;margin:1rem 0;border-radius:8px;white-space:pre-wrap}"
             "b{font-family:monospace;background:#f2c14e;padding:2px 6px;border-radius:4px}</style>",
             f"<h1>Blind comparison: {len(rows)} answers</h1><p>Rate each code 1–5 on: {', '.join(CRITERIA)}. Fill in rating_sheet.csv.</p>"]
    cur = None
    for r in rows:
        if r["prompt_id"] != cur:
            cur = r["prompt_id"]
            parts.append(f"<h2>{cur}: {html.escape(r['prompt'])}</h2>")
        parts.append(f"<article><b>{r['code']}</b>\n\n{html.escape(r['text'])}</article>")
    (B / "read.html").write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {B.relative_to(ROOT)}/read.html, rating_sheet.csv, key.json ({len(rows)} answers)")


if __name__ == "__main__":
    main()
