"""Teach Bot demo app.

An example of what the project's tutor does, running on an API model with the
Teach Bot prompt (prompts/tutor_v2.md). No fine-tuned model is involved.

    python3 -m uvicorn app.server:app --port 7860
    TEACHBOT_MODEL=kimi-k3 python3 -m uvicorn app.server:app --port 7860   # another model
    TEACHBOT_TEST=1 python3 -m uvicorn app.server:app --port 7860          # scripted, no API

Views: Lesson (the tutor, with stages, its plan, live simulators and memory),
Compare (the Teach Bot prompt vs no prompt design, same model), How it works.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import memory as M
from tools.llm import load_config, load_env
from tools.materials import ROOT, prompt, render_problems, render_weights, topic_scope
from tools.tags import THOUGHT_RE, split_stage

load_env()
CFG = json.loads((ROOT / "config" / "app.json").read_text())
MODELS = load_config()
STATIC = Path(__file__).with_name("static")
TEST_MODE = os.environ.get("TEACHBOT_TEST") == "1"
MODEL_KEY = os.environ.get("TEACHBOT_MODEL", CFG["model"])
if MODEL_KEY not in MODELS["models"]:
    raise SystemExit(f"TEACHBOT_MODEL={MODEL_KEY} is not in config/models.json")

app = FastAPI(title="Teach Bot")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# --------------------------------------------------------------------------- #
# The model
# --------------------------------------------------------------------------- #
class Model:
    def __init__(self, key: str):
        self.key = key
        self.spec = MODELS["models"][key]
        self.provider = MODELS["providers"][self.spec["provider"]]
        self._llm = None

    def info(self) -> dict:
        if TEST_MODE:
            return {"ready": True, "problem": None, "test": True}
        env = self.provider["key_env"]
        ready = bool(os.environ.get(env)) or bool(self.provider.get("no_key"))
        # Deliberately generic: the browser never learns which API model is behind the demo.
        return {"ready": ready, "test": False,
                "problem": None if ready else "No API key. Add it to the .env file and restart the app."}

    def llm(self):
        if self._llm is None:
            from tools.llm import LLM

            self._llm = LLM(self.key, MODELS)
        return self._llm

    def stream(self, messages: list[dict], temperature: float = 0.6, max_tokens: int = 1600) -> Iterator[str]:
        if TEST_MODE:
            yield from scripted_stream(messages)
            return
        yield from self.llm().stream(messages, temperature=temperature, max_tokens=max_tokens, tag="app")

    def generate(self, messages: list[dict], max_tokens: int = 600) -> str:
        return "".join(self.stream(messages, temperature=0.0, max_tokens=max_tokens))


MODEL = Model(MODEL_KEY)
print(f"[teachbot] {'TEST MODE (scripted replies)' if TEST_MODE else 'model: ' + MODEL_KEY + ' (' + MODEL.spec['model'] + ')'}; "
      f"API key {'found' if MODEL.info()['ready'] else 'MISSING'}")

SCRIPTED = """[Stage: Teach]
<thought>
- Test mode: fixed text so the interface can be checked without an API.
- Shows a plan, a formula, a simulator, a quiz and hidden answers.
</thought>

**This is fixed test text, not a model.** Picture a star's light spreading out over a sphere. The sphere's area is $4\\pi d^2$, so the light per square metre is

$$F = \\frac{L}{4\\pi d^2}$$

where $L$ is the luminosity and $d$ the distance. Ten times farther, the sphere has $10^2 = 100$ times the area, so each square gets $\\frac{1}{100}$ of the light. That is $2.5\\log_{10}100 = 5$ magnitudes fainter.

[[sim:inverse-square]]

Drag the slider to 3. How many times fainter is the star?

**Quick check**
1. A star moves 4 times farther away. What fraction of its light reaches each square?
2. Is a star of magnitude 2 brighter or fainter than one of magnitude 1?

<answers>
1. $1/4^2 = 1/16$.
2. Fainter: a larger magnitude means fainter.
</answers>

[[sim:distance-modulus]]
"""


def scripted_stream(messages: list[dict]) -> Iterator[str]:
    """TEST MODE ONLY: fixed text for interface tests; the UI labels it as not a model."""
    last = messages[-1]["content"]
    if "You keep a tutor's notes" in last:
        yield json.dumps({**M.blank_memory(), "summary": "Test mode: scripted notes, not written by a model.",
                          "skills": {**M.blank_memory()["skills"], "S1": "taught", "S2": "in progress"},
                          "misconceptions": ["ten times farther means ten times fainter"],
                          "quiz": [{"q": "4x farther", "correct": True}], "stage": "Teach"})
        return
    if "Help me with this" in last:  # the no-prompt-design condition in Compare
        text = "**Fixed test text.** Brightness falls with distance squared, so ten times farther is a hundred times fainter."
    else:
        text = SCRIPTED
    for i in range(0, len(text), 8):
        time.sleep(0.006)
        yield text[i:i + 8]


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
def tutor_system(mem: dict) -> str:
    return prompt("tutor_v2.md").format(topic_scope=topic_scope(), exam_weights=render_weights(),
                                        problems=render_problems(), memory=M.render(mem))


def plain_messages(question: str) -> list[dict]:
    lazy = prompt("lazy_baseline.md").format(topic_scope=topic_scope(), problems=render_problems())
    return [{"role": "user", "content": lazy + "\n\n" + question}]


def history_messages(rec: dict, n_turns: int) -> list[dict]:
    """Last n turns only; the saved memory carries everything older. Plans are not resent."""
    hist = rec["history"][-2 * n_turns:]
    return [{"role": h["role"], "content": THOUGHT_RE.sub("", h["content"]).strip()} for h in hist]


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def stream_response(gen) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def friendly(e: Exception) -> str:
    s = str(e)
    if "401" in s or "Authentication" in s or "api key" in s.lower():
        return "The API key was rejected. Check it in the .env file and restart the app."
    if "402" in s or "Insufficient Balance" in s:
        return "The API account is out of credit."
    if "404" in s or "model" in s.lower() and "not" in s.lower():
        return "The model name in config/models.json wasn't recognised by the API."
    if "budget" in s.lower():
        return s
    if "Connection" in type(e).__name__ or "connect" in s.lower():
        return "Couldn't reach the model's API. Check the internet connection."
    print(f"[api] {type(e).__name__}: {s[:500]}")
    return "Something went wrong talking to the API. Details are in the terminal running the app."


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
class NewLearner(BaseModel):
    name: str = ""


class ChatIn(BaseModel):
    learner_id: str
    message: str


class OneShotIn(BaseModel):
    mode: str  # "tutor" or "plain"
    message: str


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    return {"model": MODEL.info(), "test_mode": TEST_MODE,
            "study": json.loads((ROOT / "data" / "study_summary.json").read_text())}


@app.get("/api/learners")
def list_learners():
    out = []
    if M.STORE.exists():
        for p in M.STORE.glob("*.json"):
            try:
                r = json.loads(p.read_text())
            except json.JSONDecodeError:
                continue
            first = next((h["content"] for h in r["history"] if h["role"] == "user"), "")
            out.append({"id": r["id"], "name": r["name"], "created": r["created"], "turns": len(r["history"]) // 2,
                        "title": first[:60], "updated": r["history"][-1]["t"] if r["history"] else 0})
    return sorted(out, key=lambda x: x["updated"], reverse=True)[:30]


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


def _update_memory(lid: str, student: str, tutor: str) -> None:
    try:
        rec = M.load(lid)
        text = MODEL.generate(M.update_prompt(rec["memory"], student, THOUGHT_RE.sub("", tutor)), max_tokens=600)
        rec = M.load(lid)
        rec["memory"] = M.merge_update(rec["memory"], text)
        rec["memory_updates"] = rec.get("memory_updates", 0) + 1
        M.save(rec)
    except Exception as e:  # memory is best-effort; the lesson itself already streamed
        print(f"[memory] update failed: {type(e).__name__}: {e}")


@app.post("/api/chat")
def chat(body: ChatIn):
    try:
        rec = M.load(body.learner_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "no such learner")
    msg = body.message.strip()[:4000]
    if not msg:
        raise HTTPException(400, "empty message")
    info = MODEL.info()
    messages = [{"role": "system", "content": tutor_system(rec["memory"])}, *history_messages(rec, CFG["history_turns"]),
                {"role": "user", "content": msg}]

    def gen():
        if info["problem"]:
            yield sse({"type": "error", "message": info["problem"]})
            return
        parts: list[str] = []
        t0 = time.time()
        try:
            for piece in MODEL.stream(messages):
                parts.append(piece)
                yield sse({"type": "token", "text": piece})
        except Exception as e:
            yield sse({"type": "error", "message": friendly(e)})
            return
        reply = "".join(parts)
        stage, _ = split_stage(THOUGHT_RE.sub("", reply).strip())
        rec2 = M.load(body.learner_id)
        rec2["history"] += [{"role": "user", "content": msg, "t": time.time()},
                            {"role": "assistant", "content": reply, "t": time.time(), "stage": stage}]
        if stage:
            rec2["memory"]["stage"] = stage
        M.save(rec2)
        yield sse({"type": "done", "stage": stage, "seconds": round(time.time() - t0, 1)})
        threading.Thread(target=_update_memory, args=(body.learner_id, msg, reply), daemon=True).start()

    return stream_response(gen())


@app.post("/api/oneshot")
def oneshot(body: OneShotIn):
    """Compare view: the same model with the Teach Bot prompt, or with no prompt design."""
    q = body.message.strip()[:4000]
    if body.mode == "tutor":
        messages = [{"role": "system", "content": tutor_system(M.blank_memory())},
                    {"role": "user", "content": q + "\n\n(Answer this one question directly as a Teach stage lesson.)"}]
    elif body.mode == "plain":
        messages = plain_messages(q)
    else:
        raise HTTPException(400, "mode must be tutor or plain")
    info = MODEL.info()

    def gen():
        if info["problem"]:
            yield sse({"type": "error", "message": info["problem"]})
            return
        t0 = time.time()
        try:
            for piece in MODEL.stream(messages, temperature=0.3):
                yield sse({"type": "token", "text": piece})
        except Exception as e:
            yield sse({"type": "error", "message": friendly(e)})
            return
        yield sse({"type": "done", "seconds": round(time.time() - t0, 1)})

    return stream_response(gen())
