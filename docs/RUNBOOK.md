# Runbook: from nothing to a live demo

Total cost is roughly **$5 to $15**: a few dollars of Kimi API for the teaching data, about $1 to $2 of GPU time for training, and $0.35/hr while the demo is running. Check live prices before you start.

## 0. Rent the GPU (cheapest option that does everything)

**RunPod, Community Cloud, 1 × RTX A6000 (48 GB)**, listed at about $0.33/hr. Template: any "PyTorch 2.x / CUDA 12" image. Give it **100 GB** of container or volume disk.

Why this card: 48 GB trains the 14B QLoRA comfortably, and it can serve the base and fine-tuned models side by side in class. An RTX 4090 (24 GB, ~$0.34/hr) also works for training and the app's `hf` backend, just with less headroom. Vast.ai is often cheaper still for the same cards, but reliability varies by host.

Stop the pod whenever you aren't using it. A stopped pod with a volume keeps your files and costs only cents a day.

## 1. Set up (about 15 minutes, mostly the 30 GB model download)

```bash
git clone https://github.com/alfie-j/aimodelgen && cd aimodelgen
```

```bash
git checkout claude/awesome-hamilton-o8diq3
```

```bash
bash scripts/setup_gpu_box.sh
```

Then put your keys in `.env` (Moonshot is required; DeepSeek is used for the judge and the comparison).

Confirm the model IDs your accounts actually serve, and put them and their prices into `config/models.json`:

```bash
python3 -m tools.llm models moonshot
```

```bash
python3 -m tools.llm ping kimi-k3
```

## 2. Teacher comparison (optional, ~$1)

```bash
make compare && make blind
```

Read `outputs/compare/blind/read.html`, fill in `rating_sheet.csv`, then run `make summarise`.

## 3. Teaching data (about 20 to 40 minutes, a few dollars)

Run a 20-lesson trial first and read a few of them:

```bash
make seeds && python3 -m pipeline.generate --limit 20
```

Then the full run (resumable, and the budget in `config/models.json` is enforced):

```bash
make generate && make filter
```

## 4. The physics check (Alfie, about 30 to 60 minutes)

```bash
make review
```

This works through every lesson the filter couldn't decide on, plus 30 random auto-kept ones as a spot check. Press `a` to accept or `r` to reject. This is the step the films say was ours, so do it properly.

```bash
make dataset
```

## 5. Train (about 1 to 2 hours on an A6000)

```bash
make train
```

Run it inside `tmux` so a dropped SSH connection doesn't kill it. Output: `outputs/adapter/` (adapter, `run_card.json`, `metrics.jsonl`).

## 6. Evaluate base vs fine-tuned (about 30 minutes)

```bash
make eval-judge
```

Writes `outputs/eval/report.md`. Report whatever it says. If fine-tuning doesn't win, that's a finding.

## 7. Run the app

```bash
make app
```

On RunPod, expose port 7860 (Edit Pod → HTTP ports) and open the proxy URL on the classroom laptop.

**Back up `outputs/` before you stop the pod.** It holds the adapter and every number the app shows. The adapter is about 0.5 GB:

```bash
tar czf teachbot-outputs.tgz outputs/data outputs/adapter/*.json outputs/adapter/*.safetensors outputs/adapter/*.jsonl outputs/eval outputs/compare outputs/spend.jsonl
```

Optional: run it on a laptop instead of the GPU. `make export` produces a ~9 GB GGUF; then on the laptop:

```bash
ollama create teachbot -f Modelfile
```

```bash
TEACHBOT_BACKENDS=teachbot-ollama python3 -m uvicorn app.server:app --port 7860
```

On Apple silicon or a good laptop GPU this runs at usable speed. A side-by-side with the base model then needs a second GGUF of the base.
