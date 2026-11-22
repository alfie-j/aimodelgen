#!/usr/bin/env bash
# Train on however many GPUs this machine has (1 or 2 x 24 GB is enough for 14B QLoRA).
set -euo pipefail
cd "$(dirname "$0")/.."
N=$(python3 -c "import torch; print(torch.cuda.device_count())")
if [ "$N" -lt 1 ]; then echo "no GPU found"; exit 1; fi
echo "training on $N GPU(s)"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
if [ "$N" -gt 1 ]; then
  torchrun --nproc_per_node "$N" -m train.train_qlora "$@"
else
  python3 -m train.train_qlora "$@"
fi
