import importlib
import json
import os
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
    assert s["test_mode"] and s["backends"][0]["kind"] == "test" and len(s["heldout"]) == 42
    assert "Teach Bot" in client.get("/").text
    lid = client.post("/api/learners", json={"name": "Sam"}).json()["id"]
    r = client.post("/api/chat", json={"learner_id": lid, "backend": "test", "message": "hello"})
    ev = events(r)
    assert ev[-1]["type"] == "done" and ev[-1]["stage"] == "Teach"
    text = "".join(e["text"] for e in ev if e["type"] == "token")
    assert "<thought>" in text and "TEST MODE" in text
    for _ in range(50):
        rec = client.get(f"/api/learners/{lid}").json()
        if rec["memory_updates"]:
            break
        time.sleep(0.05)
    assert rec["memory_updates"] == 1 and rec["memory"]["skills"]["S1"] == "in progress"
    assert len(rec["history"]) == 2 and rec["history"][1]["backend"] == "test"
    one = events(client.post("/api/oneshot", json={"backend": "test", "message": "q"}))
    assert one[-1]["type"] == "done"
    p = client.get("/api/pipeline").json()
    assert p["study"]["groups"]["teachbot"]["n"] == 6
    assert client.get("/api/examples").status_code == 200
    assert client.post("/api/chat", json={"learner_id": lid, "backend": "nope", "message": "x"}).status_code == 404
    assert client.get("/api/learners/../../etc").status_code == 404


def test_memory_merge_rejects_garbage():
    import app.memory as M
    mem = M.blank_memory()
    assert M.merge_update(mem, "not json") == mem
    out = M.merge_update(mem, '{"skills": {"S1": "taught", "S2": "banana"}, "stage": "Nope", "quiz": [{"q": "a", "correct": true}]}')
    assert out["skills"]["S1"] == "taught" and out["skills"]["S2"] == "not started" and out["stage"] == "Diagnose"
    assert out["quiz"] == [{"q": "a", "correct": True}]
