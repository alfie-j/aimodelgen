"""Step 6: sequence-level distillation by supervised fine-tuning, with QLoRA.

Settings (the ones the films state):
  base        Qwen/Qwen2.5-14B-Instruct, loaded 4-bit NF4, double quantisation, bf16 compute
  adapter     LoRA rank 64, alpha 128, on q,k,v,o,gate,up,down projections
  schedule    cosine, peak LR 2e-4, warm-up ratio 0.05, effective batch 32, 3 epochs
  loss        only on the assistant turn: the <thought> plan AND the lesson

Single GPU:   python -m train.train_qlora
Two GPUs:     torchrun --nproc_per_node 2 -m train.train_qlora
(or just:     bash train/run.sh)

Everything about the run (settings, versions, GPUs, data counts, losses) is
written to outputs/adapter/run_card.json and outputs/adapter/metrics.jsonl.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import time
from pathlib import Path

import torch
from torch.utils.data import Dataset

ROOT = Path(__file__).resolve().parent.parent
ROLE = {"system": "system", "human": "user", "gpt": "assistant"}
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


# --------------------------------------------------------------------------- #
# Data: tokenise with the model's chat template, mask everything but assistant
# --------------------------------------------------------------------------- #
def encode(conv: list[dict], tok, max_len: int) -> dict | None:
    msgs = [{"role": ROLE[t["from"]], "content": t["value"]} for t in conv]
    full = tok.apply_chat_template(msgs, tokenize=False)
    spans = []
    for i, m in enumerate(msgs):
        if m["role"] != "assistant":
            continue
        prefix = tok.apply_chat_template(msgs[:i], tokenize=False, add_generation_prompt=True)
        upto = tok.apply_chat_template(msgs[: i + 1], tokenize=False)
        if not (full.startswith(prefix) and full.startswith(upto)):
            raise ValueError("chat template is not prefix-stable; cannot locate assistant span")
        spans.append((len(prefix), len(upto)))
    enc = tok(full, add_special_tokens=False, return_offsets_mapping=True)
    ids, offs = enc["input_ids"], enc["offset_mapping"]
    labels = [tid if any(a <= s < b for a, b in spans) else -100 for tid, (s, _e) in zip(ids, offs)]
    if len(ids) > max_len:
        return None  # dropped and counted, never silently truncated
    if all(l == -100 for l in labels):
        return None
    return {"input_ids": ids, "labels": labels}


class ChatData(Dataset):
    def __init__(self, path: Path, tok, max_len: int):
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        self.items, self.dropped = [], 0
        for r in rows:
            e = encode(r["conversations"], tok, max_len)
            if e is None:
                self.dropped += 1
            else:
                self.items.append(e)
        self.tokens = sum(len(e["input_ids"]) for e in self.items)
        self.target_tokens = sum(sum(l != -100 for l in e["labels"]) for e in self.items)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


class Collator:
    def __init__(self, pad_id: int):
        self.pad = pad_id

    def __call__(self, batch):
        n = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), n), self.pad, dtype=torch.long)
        lab = torch.full((len(batch), n), -100, dtype=torch.long)
        att = torch.zeros((len(batch), n), dtype=torch.long)
        for i, b in enumerate(batch):
            k = len(b["input_ids"])
            ids[i, :k] = torch.tensor(b["input_ids"])
            lab[i, :k] = torch.tensor(b["labels"])
            att[i, :k] = 1
        return {"input_ids": ids, "labels": lab, "attention_mask": att}


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen2.5-14B-Instruct")
    ap.add_argument("--train", default=str(ROOT / "outputs/data/train.jsonl"))
    ap.add_argument("--val", default=str(ROOT / "outputs/data/val.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "outputs/adapter"))
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--warmup-ratio", type=float, default=0.05)
    ap.add_argument("--effective-batch", type=int, default=32)
    ap.add_argument("--per-device-batch", type=int, default=2)
    ap.add_argument("--rank", type=int, default=64)
    ap.add_argument("--alpha", type=int, default=128)
    ap.add_argument("--dropout", type=float, default=0.05)
    ap.add_argument("--max-len", type=int, default=2048)
    ap.add_argument("--seed", type=int, default=1202)
    ap.add_argument("--no-4bit", action="store_true", help="CPU smoke tests only")
    ap.add_argument("--max-steps", type=int, default=-1, help="smoke tests only")
    args = ap.parse_args()

    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer,
                              TrainerCallback, TrainingArguments, set_seed)
    import transformers, peft

    set_seed(args.seed)
    world = int(os.environ.get("WORLD_SIZE", 1))
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    is_main = int(os.environ.get("RANK", 0)) == 0
    cuda = torch.cuda.is_available() and not args.no_4bit
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    grad_acc = max(1, args.effective_batch // (args.per_device_batch * world))
    eff = grad_acc * args.per_device_batch * world
    if eff != args.effective_batch and is_main:
        print(f"[warn] effective batch is {eff}, not {args.effective_batch}; adjust --per-device-batch")

    tok = AutoTokenizer.from_pretrained(args.base, use_fast=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    train_ds = ChatData(Path(args.train), tok, args.max_len)
    val_ds = ChatData(Path(args.val), tok, args.max_len) if Path(args.val).exists() and Path(args.val).stat().st_size else None
    if is_main:
        print(f"train: {len(train_ds)} examples ({train_ds.dropped} too long), {train_ds.tokens} tokens, "
              f"{train_ds.target_tokens} trained-on tokens; val: {len(val_ds) if val_ds else 0}")

    if cuda:
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                                 bnb_4bit_compute_dtype=torch.bfloat16)
        model = AutoModelForCausalLM.from_pretrained(args.base, quantization_config=bnb, torch_dtype=torch.bfloat16,
                                                     device_map={"": local_rank}, attn_implementation="sdpa")
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                                gradient_checkpointing_kwargs={"use_reentrant": False})
    else:
        model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.float32)
    model.config.use_cache = False
    lora = LoraConfig(r=args.rank, lora_alpha=args.alpha, lora_dropout=args.dropout, target_modules=TARGETS,
                      bias="none", task_type="CAUSAL_LM")
    model = get_peft_model(model, lora)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    if is_main:
        print(f"trainable params: {trainable:,} of {total:,} ({100*trainable/total:.2f}%)")

    metrics_path = out / "metrics.jsonl"
    if is_main and metrics_path.exists():
        metrics_path.unlink()

    class LogMetrics(TrainerCallback):
        def on_log(self, a, state, control, logs=None, **kw):
            if is_main and logs:
                with metrics_path.open("a") as f:
                    f.write(json.dumps({"step": state.global_step, "epoch": state.epoch, "t": time.time(), **logs}) + "\n")

    import inspect

    targ_params = inspect.signature(TrainingArguments.__init__).parameters
    # optimizer steps, counted the way Trainer counts them; warm-up is 5% of these.
    # (computed here because transformers 5 removed the warmup_ratio argument)
    steps_per_epoch = max(1, math.ceil(math.ceil(len(train_ds) / (args.per_device_batch * world)) / grad_acc))
    total_steps = args.max_steps if args.max_steps > 0 else math.ceil(steps_per_epoch * args.epochs)
    warmup_steps = math.ceil(args.warmup_ratio * total_steps)
    eval_kw = {}
    if val_ds:
        eval_kw = {"eval_steps": max(1, steps_per_epoch // 4), "per_device_eval_batch_size": args.per_device_batch}
        # the keyword was renamed in transformers 4.46
        eval_kw["eval_strategy" if "eval_strategy" in targ_params else "evaluation_strategy"] = "steps"
    targs = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.per_device_batch,
        gradient_accumulation_steps=grad_acc,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=warmup_steps,
        bf16=cuda,
        logging_steps=1 if args.max_steps > 0 else 5,
        save_strategy="epoch" if args.max_steps < 0 else "no",
        save_total_limit=3,
        optim="paged_adamw_8bit" if cuda else "adamw_torch",
        gradient_checkpointing=cuda,
        gradient_checkpointing_kwargs={"use_reentrant": False} if cuda else None,
        report_to="none",
        ddp_find_unused_parameters=False if world > 1 else None,
        remove_unused_columns=False,
        dataloader_num_workers=2 if cuda else 0,
        seed=args.seed,
        **eval_kw,
    )
    trainer = Trainer(model=model, args=targs, train_dataset=train_ds, eval_dataset=val_ds,
                      data_collator=Collator(tok.pad_token_id), callbacks=[LogMetrics()])
    t0 = time.time()
    result = trainer.train()
    final_eval = trainer.evaluate() if val_ds else {}

    if is_main:
        model.save_pretrained(out)
        tok.save_pretrained(out)
        gpus = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else []
        card = {
            "base": args.base,
            "method": "sequence-level distillation by SFT on <thought> plans + lessons",
            "quantisation": "4-bit NF4, double quantisation, bf16 compute" if cuda else "none (smoke test)",
            "lora": {"r": args.rank, "alpha": args.alpha, "dropout": args.dropout, "target_modules": TARGETS},
            "schedule": {"lr": args.lr, "scheduler": "cosine", "warmup_ratio": args.warmup_ratio, "warmup_steps": warmup_steps,
                         "total_steps": total_steps, "epochs": args.epochs,
                         "per_device_batch": args.per_device_batch, "grad_accum": grad_acc, "world_size": world,
                         "effective_batch": eff, "max_len": args.max_len, "seed": args.seed},
            "data": {"train_examples": len(train_ds), "dropped_too_long": train_ds.dropped, "train_tokens": train_ds.tokens,
                     "trained_on_tokens": train_ds.target_tokens, "val_examples": len(val_ds) if val_ds else 0},
            "trainable_params": trainable,
            "total_params": total,
            "train_loss": result.training_loss,
            "final_eval": final_eval,
            "steps": result.global_step,
            "wall_clock_min": round((time.time() - t0) / 60, 1),
            "hardware": gpus or [platform.processor() or "cpu"],
            "versions": {"torch": torch.__version__, "transformers": transformers.__version__, "peft": peft.__version__},
            "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        card_ds = ROOT / "outputs/data/dataset_card.json"
        if card_ds.exists():
            card["dataset_card"] = json.loads(card_ds.read_text())
        (out / "run_card.json").write_text(json.dumps(card, indent=2))
        print(json.dumps({k: card[k] for k in ("train_loss", "final_eval", "steps", "wall_clock_min")}, indent=2))
        print(f"adapter saved to {out}")


if __name__ == "__main__":
    main()
