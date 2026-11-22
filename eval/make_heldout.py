"""Writes eval/heldout.jsonl: questions the student model never trains on.

The wording templates here are different from the ones in materials/curriculum.json
and build_dataset.py drops any training line that overlaps them. Every answer is
computed by tools/physics.py.

    python -m eval.make_heldout
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from tools import physics as P

OUT = Path(__file__).with_name("heldout.jsonl")

# (skill, kind, template, answer function). kind sets the grading tolerance.
T = [
    ("S1", "ratio", "A torch shines on a wall {a} metres away. I step back until I'm {b} metres away. How many times dimmer is the patch of light now?",
     lambda v: (v["b"] / v["a"]) ** 2),
    ("S1", "ratio", "If our Sun were moved to {k} times its current distance from Earth, how many times less sunlight would we get?",
     lambda v: v["k"] ** 2),
    ("S1", "ratio", "Star P is {L} times more luminous than star Q, but P is {k} times farther away. How many times brighter does P look than Q?",
     lambda v: v["L"] / v["k"] ** 2),
    ("S2", "ratio", "Roughly how many times brighter is a star of magnitude {m1} than one of magnitude {m2}?",
     lambda v: P.flux_ratio_from_delta_mag(v["m1"] - v["m2"])),
    ("S2", "mag", "A star dims so that we receive only 1/{f} of its previous light. By how many magnitudes did its magnitude increase?",
     lambda v: P.delta_mag_from_flux_ratio(1 / v["f"])),
    ("S3", "mag", "What is the total magnitude of {n} identical stars that each have magnitude {m}, seen together as one point?",
     lambda v: P.combined_magnitude([v["m"]] * v["n"])),
    ("S3", "mag", "A double star has parts of magnitude {m1} and {m2}. What magnitude would a telescope that can't split them measure?",
     lambda v: P.combined_magnitude([v["m1"], v["m2"]])),
    ("S4", "distance", "A star's absolute magnitude is {M} and it appears at magnitude {m}. What is its distance in parsecs?",
     lambda v: P.distance_from_modulus(v["m"] - v["M"])),
    ("S4", "mag", "If a star with absolute magnitude {M} were placed {d} parsecs away, what apparent magnitude would we see?",
     lambda v: P.apparent_magnitude(v["M"], v["d"])),
    ("S4", "mag", "A star is {d} parsecs away and looks like magnitude {m}. What is its absolute magnitude?",
     lambda v: P.absolute_magnitude(v["m"], v["d"])),
    ("S5", "distance", "A telescope measures a parallax angle of {pmas} milliarcseconds for a star. How far away is it in parsecs?",
     lambda v: P.parallax_distance_pc(v["pmas"] / 1000)),
    ("S5", "mag", "A star shows a parallax of {p} arcseconds and has apparent magnitude {m}. Find its absolute magnitude.",
     lambda v: P.absolute_magnitude(v["m"], P.parallax_distance_pc(v["p"]))),
    ("S6", "distance", "Dust between us and a star dims it by {A} magnitudes. The star has m = {m} and M = {M}. What is its true distance in parsecs?",
     lambda v: P.distance_from_modulus(v["m"] - v["M"], v["A"])),
    ("S6", "ratio", "One star has absolute magnitude {M1}, another has absolute magnitude {M2}. How many times more luminous is the first?",
     lambda v: P.luminosity_ratio_from_abs_mags(v["M1"], v["M2"])),
]


def draw(rng: random.Random) -> dict:
    a = rng.choice([2, 3, 4, 6])
    return {
        "a": a, "b": a * rng.choice([2, 3, 5]), "k": rng.choice([3, 6, 7, 12, 30]),
        "L": rng.choice([16, 50, 200, 1000]), "m1": round(rng.uniform(-1.0, 2.0), 1),
        "m2": round(rng.uniform(3.0, 6.5), 1), "f": rng.choice([4, 16, 40, 250, 1000]),
        "n": rng.choice([2, 3, 4, 10]), "m": round(rng.uniform(7.0, 15.0), 1),
        "M": round(rng.uniform(-2.0, 5.0), 1), "d": rng.choice([25, 80, 300, 1500, 8000]),
        "pmas": rng.choice([1, 3, 12.5, 40, 125]), "p": rng.choice([0.004, 0.025, 0.08, 0.25]),
        "A": rng.choice([0.8, 1.2, 2.5]), "M1": round(rng.uniform(-6.0, 0.0), 1), "M2": round(rng.uniform(1.0, 8.0), 1),
    }


def main(per_template: int = 3, seed: int = 4242) -> None:
    rng = random.Random(seed)
    rows, seen = [], set()
    for ti, (skill, kind, tmpl, fn) in enumerate(T):
        j = 0
        while j < per_template:
            v = draw(rng)
            q = tmpl.format(**v)
            if q in seen:
                continue
            seen.add(q)
            rows.append({"id": f"H{ti:02d}-{j}", "skill": skill, "kind": kind, "question": q, "answer": float(f"{fn(v):.6g}")})
            j += 1
    with OUT.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} held-out questions to {OUT}")


if __name__ == "__main__":
    main()
