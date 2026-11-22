"""Comparison kit, step 1: run the same prompts through every candidate teacher.

Two conditions per model:
  system_v1  the Teach Bot system prompt (prompts/system_prompt_v1.md)
  lazy       no prompt design at all (prompts/lazy_baseline.md)

    python run_compare.py                    # all models in roles.compare
    python run_compare.py --models kimi-k3 deepseek-v4-pro
Results: outputs/compare/raw.jsonl (resumable). Then: python make_blind.py
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor

from tools.llm import LLM, load_config
from tools.materials import ROOT, prompt, render_problems, render_weights, topic_scope

OUT = ROOT / "outputs" / "compare" / "raw.jsonl"


def messages(condition: str, user_msg: str) -> list[dict]:
    if condition == "system_v1":
        sys = prompt("system_prompt_v1.md").format(topic_scope=topic_scope(), exam_weights=render_weights(),
                                                   problems=render_problems(), memory="Nothing yet: this is a new student.")
        return [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}]
    lazy = prompt("lazy_baseline.md").format(topic_scope=topic_scope(), problems=render_problems())
    return [{"role": "user", "content": lazy + "\n\n" + user_msg}]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--conditions", nargs="*", default=["system_v1", "lazy"])
    args = ap.parse_args()
    cfg = load_config()
    models = args.models or cfg["roles"]["compare"]
    prompts = [json.loads(l) for l in (ROOT / "inputs" / "compare_prompts.jsonl").read_text().splitlines() if l.strip()]
    done = set()
    if OUT.exists():
        done = {(r["model"], r["condition"], r["prompt_id"]) for r in map(json.loads, OUT.read_text().splitlines())}
    OUT.parent.mkdir(parents=True, exist_ok=True)

    jobs = [(m, c, p) for m in models for c in args.conditions for p in prompts if (m, c, p["id"]) not in done]
    print(f"{len(jobs)} calls to make")
    clients = {}
    for m in models:
        try:
            clients[m] = LLM(m, cfg)
        except Exception as e:
            print(f"[skip model] {m}: {e}")

    def one(job):
        m, c, p = job
        if m not in clients:
            return None
        try:
            r = clients[m].chat(messages(c, p["message"]), tag="compare")
        except Exception as e:
            print(f"[fail] {m} {c} {p['id']}: {str(e)[:120]}")
            return None
        return {"model": m, "condition": c, "prompt_id": p["id"], "prompt": p["message"], "text": r.text,
                "tokens_in": r.tokens_in, "tokens_out": r.tokens_out, "cost_usd": r.cost_usd, "seconds": round(r.seconds, 1)}

    with ThreadPoolExecutor(6) as pool, OUT.open("a") as f:
        for row in pool.map(one, jobs):
            if row:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  {row['model']:<18} {row['condition']:<10} {row['prompt_id']}  {row['tokens_out']} tok  ${row['cost_usd']:.4f}")


if __name__ == "__main__":
    main()
