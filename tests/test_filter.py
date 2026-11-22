from pipeline.filter import gate, text_physics, sign_issues
from tools.dedup import find_duplicates
from tools.tags import parse_teacher_output, training_target

PLAN = "<thought>\n- learner thinks 10x farther is 10x fainter\n- picture: spray paint on a wall spreading over a bigger area\n- steps: sphere area, ratio, magnitudes\n- check-in: what about 3x farther? expect 1/9\n</thought>"
LESSON = ("Imagine spraying paint at a wall. Step back and the same paint covers a bigger patch, so each bit is thinner. "
          "Starlight does the same: it spreads over a sphere of area $4\\pi d^2$, so the flux is $F = L/(4\\pi d^2)$, where L is "
          "the luminosity and d the distance. If you go 10 times farther, the area is 100 times bigger, so the star is 100 times fainter. "
          "Astronomers say that is 5 magnitudes fainter, because $2.5\\log_{10}100 = 5$. Worked example: a star seen from 4 pc and then "
          "from 12 pc is 3 times farther, so it gets 9 times fainter. Remember that a fainter star has a larger magnitude, so the number "
          "goes up by 5 when the light drops by 100. Your turn: if a star moves 2 times farther away, how many times fainter does it get?")
CHECKS = '<checks>[{"type": "flux_ratio_from_distance", "distance_ratio": 10, "flux_ratio": 0.01}, {"type": "delta_mag_from_flux_ratio", "flux_ratio": 0.01, "delta_mag": 5}]</checks>'


def row(text, kind="explain"):
    return {"gen_id": "x#0", "kind": kind, "text": text, "skill_id": "S1", "learner_message": "hi"}


def test_good_lesson_is_kept():
    v, g, notes = gate(row(f"{PLAN}\n\n{LESSON}\n\n{CHECKS}"))
    assert (v, g) == ("keep", ""), notes


def test_wrong_number_rejected():
    bad = CHECKS.replace('"flux_ratio": 0.01}', '"flux_ratio": 0.1}', 1)
    assert gate(row(f"{PLAN}\n\n{LESSON}\n\n{bad}"))[:2] == ("reject", "numbers")


def test_self_contradiction_rejected():
    c = '<checks>[{"type": "arithmetic", "expr": "2+2", "value": 4}, {"type": "arithmetic", "expr": "2+2", "value": 4.0001}, {"type": "distance_modulus", "d_pc": 100, "mu": 5}, {"type": "distance_modulus", "d_pc": 100, "mu": 5.04}]</checks>'
    assert gate(row(f"{PLAN}\n\n{LESSON}\n\n{c}"))[:2] == ("reject", "contradiction")


def test_prose_inverse_square_error():
    assert text_physics("Move it 10 times farther and it looks 10 times fainter.")
    assert not text_physics("Move it 10 times farther and it looks 100 times fainter.")
    assert not text_physics("ten times farther away makes it a hundred times fainter")
    bad = LESSON.replace("100 times fainter", "10 times fainter")
    assert gate(row(f"{PLAN}\n\n{bad}\n\n{CHECKS}"))[:2] == ("review", "text_physics")


def test_quoted_misconception_is_fine():
    assert not text_physics("You might think 10 times farther means 10 times fainter. It doesn't.")
    assert not text_physics("Most people guess that 3 times farther is 3 times fainter, but the area grows as the square.")


def test_sign_convention_flagged_for_review():
    assert sign_issues("A larger magnitude means a brighter star.")
    assert sign_issues("Flux is inversely proportional to the distance.")
    assert not sign_issues("Flux is inversely proportional to the distance squared.")
    bad = LESSON + " So a larger magnitude means a brighter star."
    assert gate(row(f"{PLAN}\n\n{bad}\n\n{CHECKS}"))[:2] == ("review", "sign")


def test_invented_transformation_rejected():
    bad = LESSON.replace("Worked example:", "First apply a coordinate transformation to the star's frame. Worked example:")
    assert gate(row(f"{PLAN}\n\n{bad}\n\n{CHECKS}"))[:2] == ("reject", "invented")


def test_no_check_in_rejected():
    bad = LESSON.rsplit("Your turn", 1)[0]
    assert gate(row(f"{PLAN}\n\n{bad}\n\n{CHECKS}"))[:2] == ("reject", "pedagogy")


def test_format_rejected():
    assert gate(row(f"{LESSON}\n\n{CHECKS}"))[:2] == ("reject", "format")
    assert gate(row(f"{PLAN}\n\n{LESSON}\n\n<checks>not json</checks>"))[:2] == ("reject", "format")


def test_duplicates():
    texts = [LESSON, LESSON.replace("Imagine", "Picture"), "Something entirely different about parallax and thumbs at arm's length " * 5]
    d = find_duplicates(texts)
    assert d == {1: 0}


def test_training_target_keeps_plan():
    p = parse_teacher_output(f"{PLAN}\n\n{LESSON}\n\n{CHECKS}")
    t = training_target(p.plan, p.explanation)
    assert t.startswith("<thought>") and "</thought>" in t and "<checks>" not in t and t.endswith("fainter does it get?")
