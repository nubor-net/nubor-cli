from __future__ import annotations

import pytest

from nubor.core.confirm import confirm


def test_quiet_prints_summary_but_never_prompts(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise AssertionError("prompted despite --quiet")

    monkeypatch.setattr("nubor.core.confirm.click.confirm", fail)
    confirm(["about to do a thing"], quiet=True)
    assert "about to do a thing" in capsys.readouterr().out


def test_accepting_returns(monkeypatch):
    monkeypatch.setattr("nubor.core.confirm.click.confirm", lambda *a, **k: True)
    confirm(["x"], quiet=False)


def test_declining_exits_1(monkeypatch, capsys):
    monkeypatch.setattr("nubor.core.confirm.click.confirm", lambda *a, **k: False)
    with pytest.raises(SystemExit) as excinfo:
        confirm(["x"], quiet=False)
    assert excinfo.value.code == 1
    assert "Aborted" in capsys.readouterr().err
