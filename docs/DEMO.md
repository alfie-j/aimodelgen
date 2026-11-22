# Running the Teach Bot demo

An illustrative demo of the Teach Bot student. Replies are generated live by an API model with the Teach Bot prompt (`prompts/tutor_v2.md`). The interface never names that model. It runs on any laptop: no GPU, no training.

## 1. Get the code (once)

You need Python 3.10 or newer and Git.

```bash
git clone https://github.com/alfie-j/aimodelgen
```

```bash
cd aimodelgen
```

```bash
git checkout claude/awesome-hamilton-o8diq3
```

```bash
python3 -m pip install -r requirements.txt
```

On Windows, use `py` wherever these steps say `python3`.

## 2. Connect your API key (once)

1. Go to platform.deepseek.com, sign in to the account you topped up, open **API keys**, and create a key. Copy it straight away; it's shown only once.
2. In the `aimodelgen` folder, copy the example settings file:

   ```bash
   cp .env.example .env
   ```

   (Windows: `copy .env.example .env`)
3. Open `.env` in any text editor and paste the key after `DEEPSEEK_API_KEY=`, with no spaces or quotes:

   ```
   DEEPSEEK_API_KEY=sk-your-key-here
   ```

   `.env` is in `.gitignore`, so the key is never committed. Don't share or upload this file.

4. Check the key works. This makes one tiny call (a fraction of a cent):

   ```bash
   python3 -m tools.llm ping deepseek-v4-flash
   ```

   It should print `'OK'` and some token counts. If it says the model doesn't exist, list the names your account serves:

   ```bash
   python3 -m tools.llm models deepseek
   ```

   Then put the right one in `config/models.json`, in the `"model":` field under `deepseek-v4-flash`. Pick the newest "flash" model listed.

## 3. Start the app

```bash
python3 -m uvicorn app.server:app --port 7860
```

Open http://localhost:7860. The terminal prints which model it's using and whether the key was found. In the app, the sidebar should show a green dot and **Connected**. If it says **No API key**, fix `.env` and restart the app (it reads `.env` only at start). Stop the app with Ctrl+C.

To check the interface with no API at all (fixed replies, red banner):

```bash
TEACHBOT_TEST=1 python3 -m uvicorn app.server:app --port 7860
```

## 4. Trial run (the day before)

1. Click **New lesson** and pick "Test my intuition".
2. Check the progress panel moves through the stages, and open the teaching plan.
3. When it drops in a simulator, drag it.
4. Answer a check-in question wrong on purpose. Within a few seconds the memory panel should note the misconception.
5. Ask it "what model are you?". It should say it's Teach Bot.
6. **Compare** tab: pick an example and press **Ask both**.
7. **How it works** tab: scroll through once.
8. Read the physics in its answers. They come from a live model, so check them.

## 5. On the day

- Start the app 10 minutes early and click **New lesson**, so the panels start empty.
- Use the browser's full-screen mode (F11, or Ctrl+Cmd+F on a Mac).
- If the classroom Wi-Fi blocks the API, a phone hotspot fixes it. Everything else (fonts, maths, simulators) works offline.

## Cost

10 yuan covers roughly 900 to 2,000 messages. A demo plus a trial run uses well under 1 yuan.

## If something goes wrong

| What you see | Fix |
|---|---|
| "No API key" | `.env` is missing, misnamed, or the key line has a typo. Restart after fixing. |
| "The API key was rejected" | Make a new key on the DeepSeek platform and paste it again. |
| "The API account is out of credit" | Top up on the DeepSeek platform. |
| "The model name … wasn't recognised" | Run `python3 -m tools.llm models deepseek` and update `config/models.json`. |
| "Something went wrong talking to the API" | The terminal running the app shows the full error. |
