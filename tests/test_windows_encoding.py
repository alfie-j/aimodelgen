"""Windows reads files as cp1252 unless told otherwise, which crashed the app on
the topic notes (they contain characters like ₁ and π). Every file access must
name UTF-8. This runs the app's main paths with any default-encoding access
turned into an error."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CODE = r"""
import os, tempfile
from pathlib import Path
import app.memory as M
M.STORE = Path(tempfile.mkdtemp())
from app.server import tutor_system, plain_messages
from tools.materials import render_problems, render_weights
rec = M.new_learner("Zoë")
rec["memory"]["misconceptions"].append("m₁ − m₂ = 2.5 log(F₁/F₂) π ≈ 3.14")
M.save(rec)
assert M.load(rec["id"])["memory"]["misconceptions"][0].startswith("m₁")
assert "₁" in tutor_system(rec["memory"])
plain_messages("why?"); render_problems(); render_weights()
print("ok")
"""


def test_no_default_encoding_anywhere_in_the_app():
    r = subprocess.run([sys.executable, "-X", "warn_default_encoding", "-W", "error::EncodingWarning", "-c", CODE],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stderr[-2000:]
