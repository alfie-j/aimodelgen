You are writing one lesson that will be used to train a smaller tutor model. Use the
Feynman technique: explain the idea so simply that someone who has never taken
physics can rebuild it themselves, find the gap in their understanding, and fill it.

Topic scope (use only this plus standard physics; conventions: log is base 10,
distances in parsecs, brighter means a SMALLER magnitude):
---
{topic_scope}
---

Skill: {skill_id} {skill_name}
Concept: {concept}
Misconception the learner may bring: {misconception}
Learner: {persona}

The learner's message:
"""{learner_message}"""

Reply in exactly three parts, in this order.

PART 1. A teaching plan between <thought> and </thought>. Bullet points:
- what the learner probably already pictures, and the misconception to target
- the everyday picture or analogy you will start from
- the order of steps, from picture to formula to worked numbers
- the check-in question you will end with and the answer you expect
This is a plan, not a derivation. Keep it under 150 words.

PART 2. The explanation the learner reads, under 350 words.
- start from the picture, not the formula
- one everyday analogy
- the formula with every symbol defined, LaTeX between $...$
- one worked example with real numbers, every step shown
- end with ONE short check-in question for the learner (do not answer it)
Do not introduce coordinate transformations, frames of reference, or any formula that
is not in the topic scope. Watch the sign: a fainter star has a LARGER magnitude.

PART 3. Between <checks> and </checks>, a JSON list of every numerical claim you made,
so a program can recompute it. Use only these forms (numbers as JSON numbers):
  {{"type": "flux_ratio_from_distance", "distance_ratio": 10, "flux_ratio": 0.01}}
  {{"type": "delta_mag_from_flux_ratio", "flux_ratio": 0.01, "delta_mag": 5}}
  {{"type": "flux_ratio_from_delta_mag", "delta_mag": 5, "flux_ratio": 0.01}}
  {{"type": "distance_modulus", "d_pc": 100, "mu": 5}}
  {{"type": "distance_from_modulus", "mu": 5, "d_pc": 100}}
  {{"type": "absolute_magnitude", "m": 10, "d_pc": 100, "M": 5}}
  {{"type": "apparent_magnitude", "M": 5, "d_pc": 100, "m": 10}}
  {{"type": "combined_magnitude", "mags": [1, 1], "m_total": 0.25}}
  {{"type": "parallax_distance", "p_arcsec": 0.1, "d_pc": 10}}
  {{"type": "luminosity_ratio", "M1": 0, "M2": 5, "L1_over_L2": 100}}
  {{"type": "arithmetic", "expr": "2.5*log10(100)", "value": 5}}
Any of these may also carry "extinction": A where relevant. If you made no numerical
claim, write <checks>[]</checks>.
