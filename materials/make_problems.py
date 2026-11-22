"""Writes materials/problems.jsonl: the worked problems the tutor cites.

These are original practice problems written for the rebuild, in the style of
olympiad questions; answers are computed by tools/physics.py, not typed by hand.
Add real past IOAA problems to problems_ioaa.jsonl (same fields, with a "source"
citation) and they are merged in, and counted for the exam weights.
"""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import physics as P

def r(x, n=3):
    return float(f"{x:.{n}g}")

problems = [
 ("P01", ["S1"], "A star is moved from 4 pc to 12 pc from an observer. By what factor does its flux change?",
  f"Distance ratio 3, flux ratio 1/3^2 = {r(P.flux_ratio_from_distance_ratio(3))}"),
 ("P02", ["S1","S3"], "A star is seen from 10 times farther away. How many magnitudes fainter does it appear?",
  f"Flux ratio 1/100, so Delta m = 2.5 log 100 = {r(P.delta_mag_from_flux_ratio(0.01))} mag"),
 ("P03", ["S2","S3"], "Star A has m = 1.0 and star B has m = 3.5. How many times brighter is A?",
  f"F_A/F_B = 10^(0.4*2.5) = {r(P.flux_ratio_from_delta_mag(-2.5))}"),
 ("P04", ["S3"], "A visual binary has components of magnitude 2.0 and 3.0. What is the combined magnitude?",
  f"m_total = {r(P.combined_magnitude([2.0,3.0]))}"),
 ("P05", ["S3"], "How much brighter, in magnitudes, are 100 identical stars than one of them?",
  f"Delta m = 2.5 log 100 = {r(-P.delta_mag_from_flux_ratio(100))} mag brighter"),
 ("P06", ["S4"], "A star has m = 12.0 and M = 2.0. Find its distance.",
  f"d = 10^((12-2)/5+1) = {r(P.distance_from_modulus(10.0))} pc"),
 ("P07", ["S4"], "The Sun has M = 4.83. What would its apparent magnitude be from 1 kpc?",
  f"m = 4.83 + 5 log(1000/10) = {r(P.apparent_magnitude(4.83, 1000), 4)}"),
 ("P08", ["S5"], "A star has parallax 0.025 arcsec. Find its distance in parsecs and light-years.",
  f"d = 1/0.025 = {r(P.parallax_distance_pc(0.025))} pc = {r(P.parallax_distance_pc(0.025)*P.PC_IN_LY)} ly"),
 ("P09", ["S4","S5"], "A star has parallax 5 mas and apparent magnitude 9.5. Find its absolute magnitude.",
  f"d = 200 pc, M = 9.5 - 5 log 20 = {r(P.absolute_magnitude(9.5, 200), 4)}"),
 ("P10", ["S6","S4"], "A star has m = 14.0, M = 4.0 and lies behind dust with A = 1.5 mag. Find its distance.",
  f"d = 10^((14-4-1.5)/5+1) = {r(P.distance_from_modulus(10.0, 1.5))} pc; ignoring dust would give 1000 pc"),
 ("P11", ["S6"], "Star X has M = -1.0 and star Y has M = 4.0. Find L_X / L_Y.",
  f"L_X/L_Y = 10^(0.4*5) = {r(P.luminosity_ratio_from_abs_mags(-1.0, 4.0))}"),
 ("P12", ["S1","S4"], "Two stars have the same apparent magnitude, but one is 4 times farther away. What is the difference in their absolute magnitudes?",
  f"The farther one is 16 times more luminous: Delta M = 2.5 log 16 = {r(-P.delta_mag_from_flux_ratio(16))} mag"),
]
out = Path(__file__).with_name("problems.jsonl")
with out.open("w") as f:
    for pid, skills, q, a in problems:
        f.write(json.dumps({"id": pid, "skills": skills, "question": q, "worked_answer": a,
                            "source": "practice problem written for the rebuild"}) + "\n")
print(f"wrote {len(problems)} problems to {out}")
