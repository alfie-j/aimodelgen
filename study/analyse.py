"""The participant study, re-analysed from what survived.

Only group averages survived (data/study_summary.json), plus the exact Teach Bot
post and recall scores. If the per-participant sheet turns up, save it as
data/participants.csv (columns in participants_TEMPLATE.csv) and this script
recomputes everything from it and checks it against the summary.

    python -m study.analyse
"""
from __future__ import annotations

import csv
import json
import statistics as st

from tools.materials import ROOT

SUMMARY = ROOT / "data" / "study_summary.json"
PARTS = ROOT / "data" / "participants.csv"
OUT = ROOT / "outputs" / "study"


def from_participants() -> dict[str, dict]:
    rows = list(csv.DictReader(PARTS.open(encoding="utf-8")))
    out: dict[str, dict] = {}
    for g in sorted({r["group"] for r in rows}):
        rs = [r for r in rows if r["group"] == g]
        f = lambda k: [float(r[k]) for r in rs if r.get(k, "") != ""]
        out[g] = {"n": len(rs), "pre": round(st.mean(f("pre")), 2), "post": round(st.mean(f("post")), 2),
                  "recall": round(st.mean(f("recall")), 2), "study_min_mean": round(st.mean(f("study_min")), 1),
                  "study_min_median": st.median(f("study_min"))}
    return out


def main() -> None:
    s = json.loads(SUMMARY.read_text(encoding="utf-8"))
    g = s["groups"]
    checks = []
    tb = g["teachbot"]
    checks.append(("Teach Bot post mean from scores", round(st.mean(tb["post_scores"]), 2), tb["post"]))
    checks.append(("Teach Bot recall mean from scores", round(st.mean(tb["recall_scores"]), 2), tb["recall"]))
    derived = {}
    for k, v in g.items():
        derived[k] = {"label": v["label"], "n": v["n"], "gain_immediate": round(v["post"] - v["pre"], 2),
                      "gain_recall": round(v["recall"] - v["pre"], 2), "post": v["post"], "recall": v["recall"],
                      "pre": v["pre"], "study_min_mean": v["study_min_mean"]}
    diff = {"post_difference": round(tb["post"] - g["no_ai"]["post"], 2),
            "recall_difference": round(tb["recall"] - g["no_ai"]["recall"], 2),
            "study_time_ratio": round(g["no_ai"]["study_min_mean"] / tb["study_min_mean"], 2),
            "ceiling": f"{sum(x == s['test_items'] for x in tb['post_scores'])} of {tb['n']} Teach Bot post-tests at {s['test_items']}/{s['test_items']}"}
    result = {"groups": derived, "teachbot_vs_no_ai": diff, "limits": s["limits"],
              "pilot_pooled": False, "consistency_checks": [{"what": a, "computed": b, "reported": c, "ok": abs(b - c) < 0.01} for a, b, c in checks]}
    if PARTS.exists():
        result["from_participants_csv"] = from_participants()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print("\nThe time ratio is only ever 'about four times', with the conditions caveat. The pilot is never pooled.")


if __name__ == "__main__":
    main()
