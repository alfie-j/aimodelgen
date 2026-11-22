"""CPU smoke test of train/train_qlora.py: masking, loop, metrics, run card, adapter."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("peft")
ROOT = Path(__file__).resolve().parent.parent


def lines(n):
    from tests.test_filter import LESSON, PLAN
    from tools.tags import parse_teacher_output, training_target
    p = parse_teacher_output(PLAN + LESSON + "<checks>[]</checks>")
    tgt = training_target(p.plan, p.explanation)
    return [{"id": str(i), "conversations": [{"from": "system", "value": "You are Teach Bot."},
            {"from": "human", "value": f"Question {i}: why is a far star faint?"}, {"from": "gpt", "value": tgt}]} for i in range(n)]


def test_masking(tmp_path):
    from tests.tiny_model import build
    from transformers import AutoTokenizer
    from train.train_qlora import encode
    rows = lines(2)
    d = build(tmp_path / "tiny", [t["value"] for r in rows for t in r["conversations"]])
    tok = AutoTokenizer.from_pretrained(d)
    e = encode(rows[0]["conversations"], tok, 4096)
    trained = tok.decode([i for i, l in zip(e["input_ids"], e["labels"]) if l != -100])
    assert trained.startswith("<thought>") and trained.rstrip().endswith("<|im_end|>")
    assert "Question 0" not in trained and "You are Teach Bot" not in trained
    assert encode(rows[0]["conversations"], tok, 20) is None  # too long -> dropped, not truncated


def test_train_runs(tmp_path):
    from tests.tiny_model import build
    rows = lines(24)
    d = build(tmp_path / "tiny", [t["value"] for r in rows for t in r["conversations"]])
    (tmp_path / "train.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows[:20]))
    (tmp_path / "val.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows[20:]))
    out = tmp_path / "adapter"
    cmd = [sys.executable, "-m", "train.train_qlora", "--base", str(d), "--train", str(tmp_path / "train.jsonl"),
           "--val", str(tmp_path / "val.jsonl"), "--out", str(out), "--no-4bit", "--max-steps", "6",
           "--effective-batch", "4", "--per-device-batch", "2", "--rank", "8", "--alpha", "16", "--lr", "1e-3"]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    card = json.loads((out / "run_card.json").read_text())
    assert card["steps"] == 6 and card["schedule"]["effective_batch"] == 4 and card["lora"]["r"] == 8
    assert (out / "adapter_config.json").exists()
    m = [json.loads(l) for l in (out / "metrics.jsonl").read_text().splitlines()]
    losses = [x["loss"] for x in m if "loss" in x]
    assert len(losses) >= 5 and losses[-1] < losses[0]


def test_student_adapter_switch(tmp_path):
    """HFStudent: same weights, adapter on vs off, streaming works."""
    from tests.tiny_model import build
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM
    from tools.student import HFStudent
    rows = lines(2)
    d = build(tmp_path / "tiny", [t["value"] for r in rows for t in r["conversations"]])
    m = get_peft_model(AutoModelForCausalLM.from_pretrained(d), LoraConfig(r=4, lora_alpha=8, target_modules=["q_proj", "v_proj"], init_lora_weights=False))
    m.save_pretrained(tmp_path / "ad")
    st = HFStudent(base=str(d), adapter_dir=str(tmp_path / "ad"), four_bit=False)
    msgs = [{"role": "user", "content": "why is a far star faint?"}]
    on = st.generate(msgs, adapter=True, max_new_tokens=12)
    off = st.generate(msgs, adapter=False, max_new_tokens=12)
    assert isinstance(on, str) and isinstance(off, str) and on != off
    assert "".join(st.stream(msgs, adapter=True, max_new_tokens=5, temperature=0.7)) is not None
