"""Seeds -> generate (fake teacher) -> filter -> dataset, all in a temp folder."""
import json
import sys

import pytest

from tests.test_filter import CHECKS, LESSON, PLAN


class FakeReply:
    def __init__(self, text):
        self.text, self.tokens_in, self.tokens_out, self.cost_usd, self.seconds = text, 100, 300, 0.001, 0.1


class FakeLLM:
    n = 0

    def __init__(self, *a, **k):
        pass

    def chat(self, messages, **k):
        FakeLLM.n += 1
        i = FakeLLM.n
        lesson = LESSON.replace("Imagine spraying paint", f"Lesson {i} " + " ".join(f"w{i}x{j}" for j in range(120)) + ". Imagine spraying paint")
        if i % 4 == 0:   # wrong number
            return FakeReply(f"{PLAN}\n{lesson}\n" + CHECKS.replace('"flux_ratio": 0.01}', '"flux_ratio": 0.1}', 1))
        if i % 4 == 1:   # good
            return FakeReply(f"{PLAN}\n{lesson}\n{CHECKS}")
        if i % 4 == 2:   # missing plan
            return FakeReply(f"{lesson}\n{CHECKS}")
        return FakeReply(f"{PLAN}\n{lesson} So a larger magnitude means a brighter star.\n{CHECKS}")  # to review


@pytest.fixture
def tmpdata(tmp_path, monkeypatch):
    import pipeline.build_dataset as bd
    import pipeline.filter as fl
    import pipeline.generate as gen
    import pipeline.make_seeds as ms

    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setattr(ms, "OUT", d / "seeds.jsonl")
    monkeypatch.setattr(gen, "SEEDS", d / "seeds.jsonl")
    monkeypatch.setattr(gen, "RAW", d / "raw.jsonl")
    monkeypatch.setattr(gen, "LLM", FakeLLM)
    for name in ("RAW", "KEPT", "REJECTED", "QUEUE", "REPORT"):
        monkeypatch.setattr(fl, name, d / getattr(fl, name).name)
    monkeypatch.setattr(bd, "DATA", d)
    return d


def test_e2e(tmpdata, monkeypatch):
    import pipeline.build_dataset as bd
    import pipeline.filter as fl
    import pipeline.generate as gen
    import pipeline.make_seeds as ms

    monkeypatch.setattr(sys, "argv", ["x", "--n", "40"]); ms.main()
    seeds = [json.loads(l) for l in (tmpdata / "seeds.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(seeds) == 40 and {s["kind"] for s in seeds} == {"explain", "misconception", "problem"}
    monkeypatch.setattr(sys, "argv", ["x", "--workers", "1"]); gen.main()
    monkeypatch.setattr(sys, "argv", ["x", "--workers", "1"]); gen.main()  # resumable: nothing new
    assert len((tmpdata / "raw.jsonl").read_text(encoding="utf-8").splitlines()) == 40
    monkeypatch.setattr(sys, "argv", ["x"]); fl.main()
    rep = json.loads((tmpdata / "filter_report.json").read_text(encoding="utf-8"))
    assert rep["kept_automatically"] == 10 and rep["awaiting_review"] == 10 and rep["rejected"] == 20
    assert rep["by_gate"]["numbers"]["rejected"] == 10 and rep["by_gate"]["format"]["rejected"] == 10
    # a reviewer accepts 3 queued items and rejects one auto-kept item on spot check
    q = [json.loads(l) for l in (tmpdata / "review_queue.jsonl").read_text(encoding="utf-8").splitlines()]
    k = [json.loads(l) for l in (tmpdata / "filtered.jsonl").read_text(encoding="utf-8").splitlines()]
    with (tmpdata / "review_decisions.jsonl").open("w", encoding="utf-8") as f:
        for r in q[:3]:
            f.write(json.dumps({"gen_id": r["gen_id"], "decision": "accept"}) + "\n")
        f.write(json.dumps({"gen_id": k[0]["gen_id"], "decision": "reject"}) + "\n")
    monkeypatch.setattr(sys, "argv", ["x"]); bd.main()
    card = json.loads((tmpdata / "dataset_card.json").read_text(encoding="utf-8"))
    assert card["auto_kept"] == 9 and card["accepted_after_review"] == 3
    line = json.loads((tmpdata / "train.jsonl").read_text(encoding="utf-8").splitlines()[0])
    roles = [t["from"] for t in line["conversations"]]
    assert roles == ["system", "human", "gpt"] and line["conversations"][2]["value"].startswith("<thought>")
