# Running the Teach Bot demo

The demo is an example of what the project's tutor does. It runs the Teach Bot method as a prompt (`prompts/tutor_v2.md`) on an API model. It does not train or load a model, so it runs on any laptop.

## Which model

**DeepSeek V4 Flash** (default). DeepSeek's price page lists it at about $0.14 per million input tokens and $0.28 per million output tokens. A 30-message lesson sends roughly 300k input tokens (the topic notes ride along every turn) and gets back about 40k, which is about **5 cents**. It is good at maths, and the team already has a key.

To use another model in `config/models.json` (for example `kimi-k3`, the project's teacher), set `TEACHBOT_MODEL`. Confirm the model ID your account serves first:

```bash
python3 -m tools.llm models deepseek
```

## Run it

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Put your key in `.env` (`DEEPSEEK_API_KEY=...`), then:

```bash
python3 -m uvicorn app.server:app --port 7860
```

Open http://localhost:7860. The sidebar shows a green dot and the model name when the key is set. If it says "No API key", the app reads `.env` only at start, so restart it.

To check the interface with no API at all, run it in test mode. Every reply is then fixed text, under a red banner:

```bash
TEACHBOT_TEST=1 python3 -m uvicorn app.server:app --port 7860
```

## What to show

1. **Lesson.** Pick "Test my intuition". Watch the progress panel move through the stages. Open the teaching plan. Drag the simulator the tutor drops in. Answer its question wrong on purpose and see the memory panel note the misconception.
2. **Compare.** Pick an example and press Ask both. The same model answers with the Teach Bot prompt and with the lazy baseline from the comparison kit.
3. **How it works.** The method, both simulators, the original training settings and the study results with their limits.

## What to say

"This is an example built to show what our tutor did. It runs the same teaching method as a prompt on a cheap API model. The fine-tuned model from the project isn't in it." The About box on the How it works page says the same.
