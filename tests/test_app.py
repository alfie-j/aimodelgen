import importlib
import json
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TEACHBOT_TEST", "1")
    import app.memory as M
    monkeypatch.setattr(M, "STORE", tmp_path / "learners")
    import app.server as S
    importlib.reload(S)
    return TestClient(S.app)


def events(resp):
    return [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]


def test_flow(client):
    s = client.get("/api/status").json()
    assert s["test_mode"] and s["model"]["test"] and s["study"]["groups"]["teachbot"]["n"] == 6
    assert "Teach Bot" in client.get("/").text
    lid = client.post("/api/learners", json={"name": "Sam"}).json()["id"]
    ev = events(client.post("/api/chat", json={"learner_id": lid, "message": "hello"}))
    assert ev[-1]["type"] == "done" and ev[-1]["stage"] == "Teach"
    text = "".join(e["text"] for e in ev if e["type"] == "token")
    assert "<thought>" in text and "[[sim:inverse-square]]" in text and "<answers>" in text
    for _ in range(60):
        rec = client.get(f"/api/learners/{lid}").json()
        if rec["memory_updates"]:
            break
        time.sleep(0.05)
    assert rec["memory_updates"] == 1 and rec["memory"]["skills"]["S1"] == "taught"
    assert len(rec["history"]) == 2
    lst = client.get("/api/learners").json()
    assert lst[0]["id"] == lid and lst[0]["turns"] == 1 and lst[0]["title"] == "hello"
    for mode in ("tutor", "plain"):
        assert events(client.post("/api/oneshot", json={"mode": mode, "message": "q"}))[-1]["type"] == "done"
    assert client.post("/api/oneshot", json={"mode": "x", "message": "q"}).status_code == 400
    assert client.get("/api/learners/../../etc").status_code == 404


def test_missing_key_is_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("TEACHBOT_TEST", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    import app.memory as M
    monkeypatch.setattr(M, "STORE", tmp_path / "learners")
    import tools.llm
    monkeypatch.setattr(tools.llm, "load_env", lambda *a, **k: None)
    import app.server as S
    importlib.reload(S)
    c = TestClient(S.app)
    raw = c.get("/api/status").text
    m = json.loads(raw)["model"]
    assert not m["ready"] and "No API key" in m["problem"]
    assert "deepseek" not in raw.lower() and "flash" not in raw.lower()  # the browser never learns the model
    lid = c.post("/api/learners", json={}).json()["id"]
    ev = events(c.post("/api/chat", json={"learner_id": lid, "message": "hi"}))
    assert ev[0]["type"] == "error" and "No API key" in ev[0]["message"]


def test_prompt_renders():
    import app.memory as M
    from app.server import tutor_system
    s = tutor_system(M.blank_memory())
    assert "[[sim:inverse-square]]" in s and "P06" in s and "{memory}" not in s
    assert "Do not name any AI model" in s


def test_static_files_never_name_the_model():
    from pathlib import Path
    static = Path(__file__).resolve().parent.parent / "app" / "static"
    for f in list(static.glob("*.html")) + list(static.glob("*.js")) + list(static.glob("*.css")):
        t = f.read_text().lower()
        assert "deepseek" not in t and "kimi" not in t.replace("kimi k3", ""), f.name


def test_memory_merge_rejects_garbage():
    import app.memory as M
    mem = M.blank_memory()
    assert M.merge_update(mem, "not json") == mem
    out = M.merge_update(mem, '{"skills": {"S1": "taught", "S2": "banana"}, "stage": "Nope", "quiz": [{"q": "a", "correct": true}]}')
    assert out["skills"]["S1"] == "taught" and out["skills"]["S2"] == "not started" and out["stage"] == "Diagnose"
