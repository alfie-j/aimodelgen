"""One client for every model in config/models.json.

All providers are called through their OpenAI-compatible endpoints. Every call
is logged to outputs/spend.jsonl with token counts and cost, and a provider's
budget in config/models.json is enforced before each call.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "models.json"
SPEND_LOG = ROOT / "outputs" / "spend.jsonl"

_lock = threading.Lock()


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader so no extra dependency is needed."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text())


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Reply:
    text: str
    model_key: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


def spent_by_provider() -> dict[str, float]:
    totals: dict[str, float] = {}
    if SPEND_LOG.exists():
        for line in SPEND_LOG.read_text().splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            totals[row["provider"]] = totals.get(row["provider"], 0.0) + float(row.get("cost_usd", 0))
    return totals


class LLM:
    def __init__(self, model_key: str, config: dict[str, Any] | None = None):
        load_env()
        self.config = config or load_config()
        if model_key not in self.config["models"]:
            raise KeyError(f"unknown model '{model_key}'; add it to config/models.json")
        self.key = model_key
        self.spec = self.config["models"][model_key]
        self.provider = self.spec["provider"]
        prov = self.config["providers"][self.provider]
        api_key = os.environ.get(prov["key_env"], "")
        if not api_key and not prov.get("no_key"):
            raise RuntimeError(f"set {prov['key_env']} in .env or the environment")
        from openai import OpenAI  # imported lazily so the physics/filter code needs no SDK

        self.client = OpenAI(base_url=prov["base_url"], api_key=api_key or "none", timeout=prov.get("timeout", 300))

    # ------------------------------------------------------------------ #
    def _price(self) -> tuple[float, float]:
        pin, pout = self.spec.get("price_in"), self.spec.get("price_out")
        return float(pin or 0), float(pout or 0)

    def _check_budget(self) -> None:
        budget = self.config.get("budget_usd", {}).get(self.provider)
        if budget is None:
            return
        spent = spent_by_provider().get(self.provider, 0.0)
        if spent >= budget:
            raise BudgetExceeded(f"{self.provider} budget ${budget} reached (spent ${spent:.2f})")

    def _log(self, reply: Reply, tag: str) -> None:
        SPEND_LOG.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "provider": self.provider,
            "model": self.key,
            "tag": tag,
            "tokens_in": reply.tokens_in,
            "tokens_out": reply.tokens_out,
            "cost_usd": round(reply.cost_usd, 6),
            "priced": self.spec.get("price_in") is not None,
        }
        with _lock, SPEND_LOG.open("a") as f:
            f.write(json.dumps(row) + "\n")

    def _kwargs(self, temperature: float | None, max_tokens: int | None) -> dict[str, Any]:
        kw: dict[str, Any] = {"model": self.spec["model"]}
        t = temperature if temperature is not None else self.spec.get("temperature")
        if t is not None and not self.spec.get("no_temperature"):
            kw["temperature"] = t
        mt = max_tokens or self.spec.get("max_tokens")
        if mt:
            kw["max_tokens"] = mt
        if self.spec.get("extra_body"):
            kw["extra_body"] = self.spec["extra_body"]
        return kw

    # ------------------------------------------------------------------ #
    def _without_extra(self, e: Exception, kw: dict[str, Any]) -> bool:
        """If the API rejects the model's extra settings (e.g. a 'thinking' switch it
        doesn't know), carry on without them for the rest of the session."""
        if getattr(e, "status_code", None) == 400 and "extra_body" in kw:
            del kw["extra_body"]
            self.spec = {k: v for k, v in self.spec.items() if k != "extra_body"}
            print(f"[llm] {self.key}: API rejected the extra settings; continuing without them")
            return True
        return False

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        tag: str = "",
        retries: int = 4,
    ) -> Reply:
        self._check_budget()
        kw = self._kwargs(temperature, max_tokens)
        delay = 2.0
        for attempt in range(retries + 1):
            t0 = time.time()
            try:
                resp = self.client.chat.completions.create(messages=messages, **kw)
                break
            except Exception as e:  # network / rate limit: back off and retry
                if self._without_extra(e, kw):
                    continue
                if attempt == retries or getattr(e, "status_code", None) in (400, 401, 402, 403, 404):
                    raise
                print(f"[llm] {self.key} error ({type(e).__name__}: {str(e)[:120]}); retry in {delay:.0f}s")
                time.sleep(delay)
                delay *= 2
        usage = getattr(resp, "usage", None)
        tin = getattr(usage, "prompt_tokens", 0) or 0
        tout = getattr(usage, "completion_tokens", 0) or 0
        pin, pout = self._price()
        reply = Reply(
            text=resp.choices[0].message.content or "",
            model_key=self.key,
            tokens_in=tin,
            tokens_out=tout,
            cost_usd=(tin * pin + tout * pout) / 1e6,
            seconds=time.time() - t0,
        )
        self._log(reply, tag)
        return reply

    def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        tag: str = "",
    ) -> Iterator[str]:
        self._check_budget()
        kw = self._kwargs(temperature, max_tokens)
        t0 = time.time()
        out: list[str] = []
        tin = tout = 0
        try:
            resp = self.client.chat.completions.create(
                messages=messages, stream=True, stream_options={"include_usage": True}, **kw
            )
        except Exception as e:
            if not self._without_extra(e, kw):
                raise
            resp = self.client.chat.completions.create(
                messages=messages, stream=True, stream_options={"include_usage": True}, **kw
            )
        for chunk in resp:
            if getattr(chunk, "usage", None):
                tin = chunk.usage.prompt_tokens or 0
                tout = chunk.usage.completion_tokens or 0
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                piece = chunk.choices[0].delta.content
                out.append(piece)
                yield piece
        pin, pout = self._price()
        self._log(
            Reply("".join(out), self.key, tin, tout, (tin * pin + tout * pout) / 1e6, time.time() - t0), tag
        )


def list_remote_models(provider: str) -> list[str]:
    """Ask a provider which model IDs it serves (useful to confirm IDs in models.json)."""
    load_env()
    cfg = load_config()
    prov = cfg["providers"][provider]
    from openai import OpenAI

    client = OpenAI(base_url=prov["base_url"], api_key=os.environ.get(prov["key_env"], "none"))
    return sorted(m.id for m in client.models.list())


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "models":
        print("\n".join(list_remote_models(sys.argv[2])))
    elif len(sys.argv) >= 3 and sys.argv[1] == "ping":
        r = LLM(sys.argv[2]).chat([{"role": "user", "content": "Say OK."}], max_tokens=5, tag="ping")
        print(repr(r.text), r.tokens_in, r.tokens_out, f"${r.cost_usd:.6f}")
    elif len(sys.argv) >= 2 and sys.argv[1] == "spend":
        print(json.dumps(spent_by_provider(), indent=2))
    else:
        print("usage: python -m tools.llm models <provider> | ping <model_key> | spend")
