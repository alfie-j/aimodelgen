from tools.llm import LLM


class Rejected(Exception):
    status_code = 400


def test_drops_rejected_extra_settings_once():
    o = LLM.__new__(LLM)
    o.key, o.spec = "x", {"model": "m", "extra_body": {"thinking": {"type": "disabled"}}}
    kw = {"model": "m", "extra_body": {"thinking": {"type": "disabled"}}}
    assert o._without_extra(Rejected(), kw) is True
    assert "extra_body" not in kw and "extra_body" not in o.spec
    assert o._without_extra(Rejected(), kw) is False  # second time: a real error, let it raise
