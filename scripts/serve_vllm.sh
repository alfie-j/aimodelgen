#!/usr/bin/env bash
# Serves the base model AND the fine-tuned adapter from one OpenAI-compatible
# server on :8000. Model "Qwen/Qwen2.5-14B-Instruct" = base, model "teachbot" = fine-tuned.
# A 48 GB GPU runs it in bf16. On a single 24 GB card, the app's built-in "hf"
# backend (4-bit, adapter switched on/off) is the simpler choice.
set -euo pipefail
cd "$(dirname "$0")/.."
vllm serve Qwen/Qwen2.5-14B-Instruct \
  --enable-lora --lora-modules teachbot=outputs/adapter --max-lora-rank 64 \
  --max-model-len 8192 --gpu-memory-utilization 0.92 --port 8000 "$@"
