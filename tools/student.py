"""Running the student model, before and after fine-tuning.

HFStudent loads Qwen2.5-14B-Instruct once in 4-bit with the trained adapter on
top. `adapter=False` runs the same weights with the adapter switched off, which
is exactly the base model. That gives an honest base-vs-fine-tuned comparison
from a single 24 GB GPU.

APIStudent talks to any OpenAI-compatible server (vLLM, Ollama, a provider).
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent


class HFStudent:
    def __init__(self, base: str = "Qwen/Qwen2.5-14B-Instruct", adapter_dir: str | None = None, four_bit: bool = True):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self.torch = torch
        adapter_dir = adapter_dir or str(ROOT / "outputs" / "adapter")
        self.has_adapter = Path(adapter_dir, "adapter_config.json").exists()
        cuda = torch.cuda.is_available()
        kw: dict = {}
        if cuda and four_bit:
            kw["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16)
            kw["device_map"] = "auto"
            kw["torch_dtype"] = torch.bfloat16
        self.tok = AutoTokenizer.from_pretrained(base)
        model = AutoModelForCausalLM.from_pretrained(base, **kw)
        if self.has_adapter:
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, adapter_dir, adapter_name="teachbot")
        model.eval()
        self.model = model
        self.lock = threading.Lock()  # one generation at a time on the GPU
        self.base_name = base

    def _ctx(self, adapter: bool):
        import contextlib

        if self.has_adapter and not adapter:
            return self.model.disable_adapter()
        if adapter and not self.has_adapter:
            raise RuntimeError("no trained adapter found in outputs/adapter")
        return contextlib.nullcontext()

    def _inputs(self, messages):
        text = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        return self.tok(text, return_tensors="pt").to(self.model.device)

    def generate(self, messages, adapter: bool = True, max_new_tokens: int = 900, temperature: float = 0.0) -> str:
        return "".join(self.stream(messages, adapter, max_new_tokens, temperature))

    def stream(self, messages, adapter: bool = True, max_new_tokens: int = 900, temperature: float = 0.7) -> Iterator[str]:
        from transformers import TextIteratorStreamer

        streamer = TextIteratorStreamer(self.tok, skip_prompt=True, skip_special_tokens=True)
        inputs = self._inputs(messages)
        gen_kw = dict(**inputs, max_new_tokens=max_new_tokens, streamer=streamer,
                      do_sample=temperature > 0, pad_token_id=self.tok.eos_token_id)
        if temperature > 0:
            gen_kw.update(temperature=temperature, top_p=0.9)

        def run():
            with self.lock, self.torch.no_grad(), self._ctx(adapter):
                self.model.generate(**gen_kw)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        yield from streamer
        t.join()


class APIStudent:
    def __init__(self, model_key: str):
        from tools.llm import LLM

        self.llm = LLM(model_key)
        self.key = model_key

    def generate(self, messages, max_new_tokens: int = 900, temperature: float = 0.0, **_) -> str:
        return self.llm.chat(messages, temperature=temperature, max_tokens=max_new_tokens, tag="student").text

    def stream(self, messages, max_new_tokens: int = 900, temperature: float = 0.7, **_) -> Iterator[str]:
        yield from self.llm.stream(messages, temperature=temperature, max_tokens=max_new_tokens, tag="app")
