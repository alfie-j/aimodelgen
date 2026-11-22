#!/usr/bin/env bash
# Optional: merge the adapter into the base model and make a ~9 GB GGUF so the
# tutor can run on a laptop with Ollama or llama.cpp, no GPU server needed.
# Needs ~32 GB of RAM and ~60 GB of disk. Run on the GPU box after training.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
base = "Qwen/Qwen2.5-14B-Instruct"
m = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.bfloat16, device_map="cpu")
m = PeftModel.from_pretrained(m, "outputs/adapter").merge_and_unload()
m.save_pretrained("outputs/merged", safe_serialization=True)
AutoTokenizer.from_pretrained("outputs/adapter").save_pretrained("outputs/merged")
print("merged model in outputs/merged")
PY
[ -d outputs/llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp outputs/llama.cpp
pip install -q -r outputs/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt
python3 outputs/llama.cpp/convert_hf_to_gguf.py outputs/merged --outtype bf16 --outfile outputs/teachbot-bf16.gguf
(cd outputs/llama.cpp && cmake -B build -DGGML_CUDA=OFF >/dev/null && cmake --build build --target llama-quantize -j >/dev/null)
outputs/llama.cpp/build/bin/llama-quantize outputs/teachbot-bf16.gguf outputs/teachbot-Q4_K_M.gguf Q4_K_M
cat > outputs/Modelfile <<'MF'
FROM ./teachbot-Q4_K_M.gguf
TEMPLATE """{{- if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{- range .Messages }}<|im_start|>{{ .Role }}
{{ .Content }}<|im_end|>
{{ end }}<|im_start|>assistant
"""
PARAMETER stop "<|im_end|>"
PARAMETER temperature 0.7
MF
echo "done: outputs/teachbot-Q4_K_M.gguf  (laptop: cd outputs && ollama create teachbot -f Modelfile)"
