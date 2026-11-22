#!/usr/bin/env bash
# One-time setup on a rented GPU machine (RunPod / Vast.ai, Ubuntu + CUDA image).
#   git clone <this repo> && cd aimodelgen && bash scripts/setup_gpu_box.sh
set -euo pipefail
cd "$(dirname "$0")/.."
nvidia-smi --query-gpu=name,memory.total --format=csv
python3 -m pip install -q --upgrade pip
python3 -m pip install -q -r requirements.txt -r requirements-gpu.txt
[ -f .env ] || { cp .env.example .env; echo "fill in API keys in .env"; }
# pre-download the base model (~30 GB) so training starts straight away
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen2.5-14B-Instruct', allow_patterns=['*.json','*.safetensors','*.txt','tokenizer*'])"
python3 -m pytest -q tests
echo "ready. next: make data"
