# Teach Bot: the whole pipeline. Run from the repo root. See docs/RUNBOOK.md.
PY ?= python3
N  ?= 1200       # learner prompts to generate lessons for
W  ?= 8          # parallel API calls

.PHONY: help test compare blind summarise seeds generate filter review dataset data train eval eval-judge app app-test study export
help:
	@grep -E '^[a-z-]+:.*##' Makefile | sed 's/:.*##/\t/'

test:        ## run all tests (CPU, no keys needed)
	$(PY) -m pytest -q tests
compare:     ## 1a run candidate teachers on the comparison prompts
	$(PY) run_compare.py
blind:       ## 1b anonymise outputs for rating
	$(PY) make_blind.py
summarise:   ## 1c un-blind ratings and summarise
	$(PY) summarise.py
seeds:       ## 2a write learner prompts
	$(PY) -m pipeline.make_seeds --n $(N)
generate:    ## 2b teacher writes plan + lesson for each (resumable)
	$(PY) -m pipeline.generate --workers $(W)
filter:      ## 3  physics filter (+ judge model)
	$(PY) -m pipeline.filter --judge
review:      ## 4  human physics check of flagged lessons
	$(PY) -m pipeline.review --spot-check 30
dataset:     ## 5  ShareGPT training lines
	$(PY) -m pipeline.build_dataset
data: seeds generate filter   ## 2-3 in one go
train:       ## 6  QLoRA fine-tune (GPU)
	bash train/run.sh
eval:        ## 7  base vs fine-tuned on held-out questions (GPU)
	$(PY) -m eval.run_eval --backend hf
eval-judge:  ## 7+ same, plus blind judge model
	$(PY) -m eval.run_eval --backend hf --judge
study:       ## participant study summary
	$(PY) -m study.analyse
app:         ## tutor web app on :7860 (GPU)
	TEACHBOT_BACKENDS=teachbot-hf,base-hf $(PY) -m uvicorn app.server:app --host 0.0.0.0 --port 7860
app-test:    ## app with a scripted test backend, for UI work without a GPU
	TEACHBOT_TEST=1 $(PY) -m uvicorn app.server:app --port 7860
export:      ## merge + GGUF for running on a laptop with Ollama
	bash train/export_gguf.sh
