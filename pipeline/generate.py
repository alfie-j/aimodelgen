"""Step 2: ask the teacher (Kimi K3 by default) for a plan + lesson for every seed.

Resumable: seeds already in raw.jsonl are skipped, so you can stop and restart.
Every call is costed in outputs/spend.jsonl and the provider budget is enforced.

    python -m pipeline.generate --workers 8            # all seeds
    python -m pipeline.generate --limit 20             # a quick trial first
"""
from __future__ import annotations

import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tools.llm import LLM, BudgetExceeded, load_config
from tools.materials import ROOT, prompt, topic_scope

SEEDS = ROOT / "outputs" / "data" / "seeds.jsonl"
RAW = ROOT / "outputs" / "data" / "raw.jsonl"
_write = threading.Lock()


def build_messages(seed: dict, scope: str, meta: str) -> list[dict[str, str]]:
    return [
        {
            "role": "user",
            "content": meta.format(
                topic_scope=scope,
                skill_id=seed["skill_id"],
                skill_name=seed["skill_name"],
                concept=seed["concept"],
                misconception=seed["misconception"],
                persona=seed["persona"],
                learner_message=seed["learner_message"],
            ),
        }
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", default=None, help="model key (default: roles.teacher)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--samples", type=int, default=1, help="answers per seed (more = more to filter from)")
    args = ap.parse_args()

    cfg = load_config()
    teacher = args.teacher or cfg["roles"]["teacher"]
    llm = LLM(teacher, cfg)
    seeds = [json.loads(l) for l in SEEDS.read_text().splitlines() if l.strip()]
    done: set[str] = set()
    if RAW.exists():
        done = {json.loads(l)["gen_id"] for l in RAW.read_text().splitlines() if l.strip()}
    jobs = [(s, k) for s in seeds for k in range(args.samples) if f"{s['id']}#{k}" not in done]
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"teacher={teacher}  to do={len(jobs)}  already done={len(done)}")
    scope, meta = topic_scope(), prompt("feynman_meta.md")

    def work(seed: dict, k: int) -> dict:
        r = llm.chat(build_messages(seed, scope, meta), tag="generate")
        return {
            **seed,
            "gen_id": f"{seed['id']}#{k}",
            "teacher": teacher,
            "text": r.text,
            "tokens_in": r.tokens_in,
            "tokens_out": r.tokens_out,
            "cost_usd": r.cost_usd,
        }

    RAW.parent.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    with ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(work, s, k): s["id"] for s, k in jobs}
        for fut in as_completed(futs):
            try:
                row = fut.result()
            except BudgetExceeded as e:
                print(f"[stop] {e}")
                pool.shutdown(cancel_futures=True)
                break
            except Exception as e:
                print(f"[skip] {futs[fut]}: {type(e).__name__}: {str(e)[:160]}")
                continue
            with _write, RAW.open("a") as f:
                f.write(json.dumps(row) + "\n")
            n_ok += 1
            if n_ok % 25 == 0:
                print(f"  {n_ok}/{len(jobs)}")
    print(f"done: {n_ok} new generations in {RAW}")


if __name__ == "__main__":
    main()
