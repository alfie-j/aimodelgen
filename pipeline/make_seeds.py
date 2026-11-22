"""Step 1: write the learner prompts the teacher will answer.

Every seed combines a skill, a concept, a misconception the learner might bring,
a learner persona and a kind of request (explain / challenge a misconception /
work a problem). Problems get fresh numbers from a fixed random seed, so the
file is reproducible.

    python -m pipeline.make_seeds --n 1200
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
from pathlib import Path

from tools.materials import ROOT, curriculum

OUT = ROOT / "outputs" / "data" / "seeds.jsonl"


def fill_problem(template: str, rng: random.Random) -> str:
    a = rng.choice([1, 2, 3, 4, 5])
    vals = {
        "a": a,
        "b": a * rng.choice([2, 3, 4, 5, 10]),
        "k": rng.choice([2, 3, 4, 5, 8, 10, 20]),
        "m1": round(rng.uniform(-1.5, 4.0), 1),
        "m2": round(rng.uniform(1.0, 6.0), 1),
        "dm": rng.choice([1, 2, 2.5, 3, 5, 7.5, 10]),
        "m": round(rng.uniform(6.0, 16.0), 1),
        "M": round(rng.uniform(-3.0, 6.0), 1),
        "d": rng.choice([5, 20, 40, 50, 250, 500, 2000, 5000]),
        "p": rng.choice([0.5, 0.2, 0.05, 0.04, 0.02, 0.01, 0.002]),
        "pmas": rng.choice([2, 4, 5, 8, 10, 20, 25]),
        "A": rng.choice([0.5, 1.0, 1.5, 2.0, 3.0]),
        "M1": round(rng.uniform(-5.0, 2.0), 1),
        "M2": round(rng.uniform(2.0, 9.0), 1),
    }
    return template.format(**vals)


def make_seeds(n: int, seed: int = 1202) -> list[dict]:
    rng = random.Random(seed)
    cur = curriculum()
    req = cur["requests"]
    combos = []
    for sid, sk in cur["skills"].items():
        for concept, mis in itertools.product(sk["concepts"], sk["misconceptions"]):
            combos.append((sid, sk["name"], concept, mis))
    rng.shuffle(combos)

    kinds = ["explain"] * 4 + ["misconception"] * 3 + ["problem"] * 3
    seeds, seen = [], set()
    i = 0
    while len(seeds) < n and i < n * 20:
        sid, sname, concept, mis = combos[i % len(combos)]
        i += 1
        kind = rng.choice(kinds)
        persona = rng.choice(cur["personas"])
        tmpl = rng.choice(req[kind])
        if kind == "problem":
            problem = fill_problem(rng.choice(cur["problem_templates"][sid]), rng)
            msg = tmpl.format(problem=problem)
        else:
            msg = tmpl.format(concept=concept, misconception=mis)
        key = (msg, persona)
        if key in seen:
            continue
        seen.add(key)
        seeds.append(
            {
                "id": f"seed-{len(seeds):05d}",
                "skill_id": sid,
                "skill_name": sname,
                "concept": concept,
                "misconception": mis,
                "persona": persona,
                "kind": kind,
                "learner_message": msg,
            }
        )
    return seeds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1200)
    ap.add_argument("--seed", type=int, default=1202)
    args = ap.parse_args()
    seeds = make_seeds(args.n, args.seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        for s in seeds:
            f.write(json.dumps(s) + "\n")
    by_skill: dict[str, int] = {}
    for s in seeds:
        by_skill[s["skill_id"]] = by_skill.get(s["skill_id"], 0) + 1
    print(f"wrote {len(seeds)} seeds to {OUT}  by skill: {by_skill}")


if __name__ == "__main__":
    main()
