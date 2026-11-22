import json
from pathlib import Path

import pytest
from eval.run_eval import final_answer, is_correct, mcnemar_exact, parse_number, wilson
from eval.make_heldout import T, draw
from tools import physics as P

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("s,v", [("9", 9), ("1/9", 1 / 9), ("about 2.51 times", 2.51), ("$-0.75$", -0.75),
                                 ("1,000 pc", 1000), ("3.1 × 10^4 pc", 31000), ("3.1e4", 31000), ("−1.2 mag", -1.2)])
def test_parse_number(s, v):
    assert parse_number(s) == pytest.approx(v)


def test_final_answer_and_grading():
    assert final_answer("blah\nFinal answer: 25 times dimmer") == 25
    assert final_answer("no answer") is None
    assert is_correct("ratio", 1 / 9, 9)          # "9 times dimmer" for a ratio of 1/9
    assert is_correct("mag", 5.0, 5.04) and not is_correct("mag", 5.0, 5.2)
    assert is_correct("distance", 1000, 1010) and not is_correct("distance", 1000, 1100)


def test_stats():
    lo, hi = wilson(30, 42)
    assert 0.55 < lo < 0.6 and 0.8 < hi < 0.86
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(0, 10) < 0.01


def test_heldout_answers_recompute():
    rows = [json.loads(l) for l in (ROOT / "eval" / "heldout.jsonl").read_text().splitlines()]
    assert len(rows) == 42 and len({r["question"] for r in rows}) == len(rows)
    for r in rows:
        assert r["answer"] == r["answer"] and r["answer"] != 0  # finite, non-zero
