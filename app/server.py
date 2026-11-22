"""Teach Bot web app.

    TEACHBOT_BACKENDS=teachbot-hf,base-hf uvicorn app.server:app --host 0.0.0.0 --port 7860

Tabs: Lesson (the tutor, with stages, its teaching plan and persistent memory),
Base vs fine-tuned (same question to both, side by side), and How it was built
(every number read live from the pipeline's output files).
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import memory as M
from tools.materials import ROOT, prompt, render_problems, render_weights, topic_scope
from tools.tags import THOUGHT_RE, split_stage

CFG = json.loads((ROOT / "config" / "app.json").read_text())
STATIC = Path(__file__).with_name("static")
OUT = ROOT / "outputs"
TEST_MODE = os.environ.get("TEACHBOT_TEST") == "1"

app = FastAPI(title="Teach Bot")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #
_hf = None
_hf_lock = threading.Lock()


def hf_student():
    global _hf
    with _hf_lock:
        if _hf is None:
            from tools.student import HFStudent

            _hf = HFStudent()
    return _hf


class Backend:
    def __init__(self, bid: str, spec: dict):
        self.id, self.spec = bid, spec
        self._api = None

    def info(self) -> dict:
        return {"id": self.id, **{k: self.spec[k] for k in ("label", "detail", "kind")}}

    def stream(self, messages: list[dict], temperature: float = 0.7, max_new_tokens: int = 1100) -> Iterator[str]:
        t = self.spec["type"]
        if t == "hf":
            yield from hf_student().stream(messages, adapter=self.spec["adapter"], temperature=temperature,
                                           max_new_tokens=max_new_tokens)
        elif t == "api":
            if self._api is None:
                from tools.student import APIStudent

                self._api = APIStudent(self.spec["model"])
            yield from self._api.stream(messages, temperature=temperature, max_new_tokens=max_new_tokens)
        elif t == "test":
            yield from scripted_stream(messages)
        else:
            raise RuntimeError(f"unknown backend type {t}")

    def generate(self, messages: list[dict], max_new_tokens: int = 500) -> str:
        return "".join(self.stream(messages, temperature=0.0, max_new_tokens=max_new_tokens))


def scripted_stream(messages: list[dict]) -> Iterator[str]:
    """TEST MODE ONLY (TEACHBOT_TEST=1): fixed text for UI tests, labelled in the UI as not a model."""
    last = messages[-1]["content"]
    if "You keep a tutor's notes" in last:
        yield json.dumps({**M.blank_memory(), "summary": "TEST MODE: scripted memory, not written by a model.",
                          "skills": {**M.blank_memory()["skills"], "S1": "in progress"}, "stage": "Teach"})
        return
    text = ("[Stage: Teach]\n<thought>\n- TEST MODE: scripted text, not model output.\n</thought>\n\n"
            "**Test backend.** This is fixed text used to check the interface. Light spreads over a sphere of area "
            "$4\\pi d^2$, so ten times farther gives $\\frac{1}{100}$ of the flux, which is $2.5\\log_{10}100 = 5$ "
            "magnitudes.\n\nWhat happens at three times the distance?")
    for i in range(0, len(text), 6):
        time.sleep(0.01)
        yield text[i:i + 6]


def enabled_backends() -> dict[str, Backend]:
    ids = [b.strip() for b in os.environ.get("TEACHBOT_BACKENDS", CFG["default_backends"]).split(",") if b.strip()]
    out = {i: Backend(i, CFG["backends"][i]) for i in ids if i in CFG["backends"]}
    if TEST_MODE:
        out = {"test": Backend("test", {"label": "TEST BACKEND", "detail": "scripted text for interface tests, not a model",
                                        "kind": "test", "type": "test"})}
    return out


BACKENDS = enabled_backends()


def backend(bid: str) -> Backend:
    if bid not in BACKENDS:
        raise HTTPException(404, f"backend '{bid}' not enabled")
    return BACKENDS[bid]


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
def tutor_system(mem: dict) -> str:
    return prompt("system_prompt_v1.md").format(topic_scope=topic_scope(), exam_weights=render_weights(),
                                                problems=render_problems(), memory=M.render(mem))


def history_messages(rec: dict, n_turns: int) -> list[dict]:
    """Last n turns only; the persistent memory carries everything older. Plans are not resent."""
    hist = rec["history"][-2 * n_turns:]
    return [{"role": h["role"], "content": THOUGHT_RE.sub("", h["content"]).strip()} for h in hist]


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
class NewLearner(BaseModel):
    name: str = ""


class ChatIn(BaseModel):
    learner_id: str
    backend: str
    message: str


class OneShotIn(BaseModel):
    backend: str
    message: str
    temperature: float = 0.0


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    adapter = OUT / "adapter" / "adapter_config.json"
    return {"backends": [b.info() for b in BACKENDS.values()], "test_mode": TEST_MODE,
            "adapter_present": adapter.exists(), "heldout": _load_jsonl(ROOT / "eval" / "heldout.jsonl")}


@app.post("/api/learners")
def create_learner(body: NewLearner):
    return M.new_learner(body.name)


@app.get("/api/learners/{lid}")
def get_learner(lid: str):
    try:
        return M.load(lid)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "no such learner")


@app.delete("/api/learners/{lid}")
def delete_learner(lid: str):
    try:
        M.path(lid).unlink(missing_ok=True)
    except ValueError:
        raise HTTPException(404, "no such learner")
    return {"ok": True}


def _update_memory(lid: str, b: Backend, student: str, tutor: str) -> None:
    try:
        rec = M.load(lid)
        text = b.generate(M.update_prompt(rec["memory"], student, THOUGHT_RE.sub("", tutor)), max_new_tokens=500)
        rec = M.load(lid)  # reload: the learner may have sent another message meanwhile
        rec["memory"] = M.merge_update(rec["memory"], text)
        rec["memory_updates"] = rec.get("memory_updates", 0) + 1
        M.save(rec)
    except Exception as e:  # memory is best-effort; the lesson itself already streamed
        print(f"[memory] update failed: {type(e).__name__}: {e}")


@app.post("/api/chat")
def chat(body: ChatIn):
    b = backend(body.backend)
    try:
        rec = M.load(body.learner_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "no such learner")
    msg = body.message.strip()[:4000]
    if not msg:
        raise HTTPException(400, "empty message")
    messages = [{"role": "system", "content": tutor_system(rec["memory"])}, *history_messages(rec, CFG["history_turns"]),
                {"role": "user", "content": msg}]

    def gen():
        parts: list[str] = []
        t0 = time.time()
        try:
            for piece in b.stream(messages):
                parts.append(piece)
                yield sse({"type": "token", "text": piece})
        except Exception as e:
            yield sse({"type": "error", "message": f"{type(e).__name__}: {str(e)[:300]}"})
            return
        reply = "".join(parts)
        stage, _ = split_stage(THOUGHT_RE.sub("", reply).strip())
        rec2 = M.load(body.learner_id)
        rec2["history"] += [{"role": "user", "content": msg, "t": time.time()},
                            {"role": "assistant", "content": reply, "t": time.time(), "backend": b.id, "stage": stage}]
        if stage:
            rec2["memory"]["stage"] = stage
        M.save(rec2)
        yield sse({"type": "done", "stage": stage, "seconds": round(time.time() - t0, 1), "backend": b.info()})
        threading.Thread(target=_update_memory, args=(body.learner_id, b, msg, reply), daemon=True).start()

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/oneshot")
def oneshot(body: OneShotIn):
    """For the side-by-side view: the student system prompt the model was trained with, no memory."""
    b = backend(body.backend)
    messages = [{"role": "system", "content": prompt("student_system.md").strip()},
                {"role": "user", "content": body.message.strip()[:4000]}]

    def gen():
        t0, n = time.time(), 0
        try:
            for piece in b.stream(messages, temperature=body.temperature):
                n += 1
                yield sse({"type": "token", "text": piece})
        except Exception as e:
            yield sse({"type": "error", "message": f"{type(e).__name__}: {str(e)[:300]}"})
            return
        yield sse({"type": "done", "seconds": round(time.time() - t0, 1), "chunks": n, "backend": b.info()})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- #
# "How it was built": everything read from the pipeline's own output files
# --------------------------------------------------------------------------- #
def _load_json(p: Path):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _load_jsonl(p: Path, limit: int | None = None) -> list:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if limit and len(rows) >= limit:
            break
    return rows


def _spend() -> dict:
    out: dict = {}
    for r in _load_jsonl(OUT / "spend.jsonl"):
        k = f"{r['model']}:{r.get('tag', '')}"
        o = out.setdefault(k, {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
        o["calls"] += 1
        o["tokens_in"] += r["tokens_in"]
        o["tokens_out"] += r["tokens_out"]
        o["cost_usd"] = round(o["cost_usd"] + r["cost_usd"], 4)
    return out


@app.get("/api/pipeline")
def pipeline():
    data = OUT / "data"
    metrics = _load_jsonl(OUT / "adapter" / "metrics.jsonl")
    loss = [{"step": m["step"], "epoch": m.get("epoch"), "loss": m["loss"]} for m in metrics if "loss" in m]
    eval_loss = [{"step": m["step"], "epoch": m.get("epoch"), "loss": m["eval_loss"]} for m in metrics if "eval_loss" in m]
    return JSONResponse({
        "compare": _load_json(OUT / "compare" / "summary.json"),
        "compare_runs": len(_load_jsonl(OUT / "compare" / "raw.jsonl")),
        "seeds": len(_load_jsonl(data / "seeds.jsonl")),
        "generated": len(_load_jsonl(data / "raw.jsonl")),
        "filter": _load_json(data / "filter_report.json"),
        "reviewed": len(_load_jsonl(data / "review_decisions.jsonl")),
        "dataset": _load_json(data / "dataset_card.json"),
        "run_card": _load_json(OUT / "adapter" / "run_card.json"),
        "loss": loss,
        "eval_loss": eval_loss,
        "eval": _load_json(OUT / "eval" / "report.json"),
        "study": _load_json(ROOT / "data" / "study_summary.json"),
        "spend": _spend(),
    })


@app.get("/api/examples")
def examples():
    """A few real records from each stage of the filter, for the walkthrough."""
    data = OUT / "data"
    kept = _load_jsonl(data / "filtered.jsonl", 3)
    rejected_all = _load_jsonl(data / "rejected.jsonl")
    by_gate: dict[str, dict] = {}
    for r in rejected_all:
        g = r.get("filter", {}).get("gate", "?")
        by_gate.setdefault(g, r)
    slim = lambda r: {"gen_id": r.get("gen_id"), "skill": r.get("skill_id"), "learner": r.get("learner_message"),
                      "plan": r.get("plan"), "explanation": r.get("explanation"), "checks": r.get("checks"),
                      "filter": r.get("filter")}
    return {"kept": [slim(r) for r in kept], "rejected": [slim(r) for r in by_gate.values()]}
