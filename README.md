# Teach Bot

An AI tutor for one small piece of olympiad astronomy: how bright a star looks and how far away it is (inverse-square law, magnitudes, distance modulus). A large teacher model (Kimi K3) writes physics-checked lessons; a small student (Qwen2.5-14B-Instruct) is fine-tuned on them with QLoRA so it can run on a single GPU or a laptop.

DSAI1202 · LEC008 Group 4 · Alfie Jesson John, Fung Sum Ming. This repository is a rebuild of the original project (see [docs/DEMO_DAY.md](docs/DEMO_DAY.md)).

**To run the demo: [docs/DEMO.md](docs/DEMO.md).** It's an example of what the tutor does: the Teach Bot method as a prompt on an API model (DeepSeek V4 Flash by default, a few cents per lesson). No GPU, no training. Short version: put `DEEPSEEK_API_KEY` in `.env`, then `make app`.

The full training pipeline below is kept in the repository for reference. To run it on a GPU, see [docs/RUNBOOK.md](docs/RUNBOOK.md).

## Pipeline

| Step | Command | What happens | Output |
|---|---|---|---|
| 1 Choose a teacher | `make compare blind summarise` | Candidates answer the same prompts with the Teach Bot system prompt and with a lazy baseline; you rate them blind | `outputs/compare/` |
| 2 Generate | `make seeds generate` | Feynman meta-prompt: a `<thought>` plan, the lesson, and a `<checks>` JSON of every number used | `outputs/data/raw.jsonl` |
| 3 Filter | `make filter` | Recomputes every number (`tools/physics.py`); rejects contradictions, invented coordinate transformations, missing check-ins and near-duplicates; flags sign slips and doubtful prose; an optional judge model flags more | `filtered.jsonl`, `rejected.jsonl`, `review_queue.jsonl` |
| 4 Physics check | `make review` | A human accepts or rejects each flagged lesson, plus a spot check | `review_decisions.jsonl` |
| 5 Dataset | `make dataset` | ShareGPT lines; drops anything overlapping the held-out test | `train.jsonl`, `val.jsonl`, `dataset_card.json` |
| 6 Train | `make train` | QLoRA: 4-bit NF4 with double quantisation, bf16 compute, LoRA r 64 / α 128 on all 7 projections, cosine LR 2e-4, warm-up 0.05, effective batch 32, 3 epochs, loss on plan + lesson only | `outputs/adapter/` + `run_card.json` |
| 7 Evaluate | `make eval-judge` | Base vs fine-tuned on 42 held-out questions: answer accuracy with 95% CI and exact McNemar test, plan and check-in rates, and a blind judge | `outputs/eval/report.md` |
| App | `make app` | Tutor with five stages (Diagnose → Map → Plan → Teach → Check), visible teaching plan, persistent per-learner memory, live side by side, and a "how it was built" page reading the files above | `localhost:7860` |

## Layout

```
config/       models.json (providers, prices, budgets), app.json (app backends)
prompts/      system_prompt_v1.md, lazy_baseline.md, feynman_meta.md, student_system.md
materials/    topic_scope.md (S1–S6), curriculum.json, problems.jsonl (+ problems_ioaa.jsonl if added)
tools/        physics.py (single source of truth), llm.py, tags.py, dedup.py, student.py
pipeline/     make_seeds, generate, filter, review, build_dataset
train/        train_qlora.py, run.sh, export_gguf.sh
eval/         make_heldout.py, heldout.jsonl, run_eval.py
app/          server.py, memory.py, static/ (UI, with marked + KaTeX vendored for offline use)
study/        analyse.py; data/study_summary.json holds the surviving group averages
tests/        47 tests, including a CPU training smoke test on a tiny model
```

## Notes on honesty built into the code

- Every reply in the app is labelled with the model that wrote it. Test mode (`make app-test`) shows a red "not a model" banner.
- The "how it was built" page shows "not run yet" until a step has really produced its file; nothing is hard-coded.
- Unreviewed flagged lessons never enter training. Nothing is truncated silently: over-long examples are dropped and counted.
- The study pilot is never pooled with the main groups, and the time ratio is shown only with its caveat.
- `materials/problems.jsonl` holds original practice problems written for the rebuild. Add real past IOAA problems, with citations, to `materials/problems_ioaa.jsonl`; they are merged in and counted for the exam weights.
