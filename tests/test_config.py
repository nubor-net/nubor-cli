from __future__ import annotations

import pytest

from nubor.core import config


def _capture_connect(monkeypatch):
    calls = {}

    def fake_connect(**kwargs):
        calls["kwargs"] = kwargs
        return "conn"

    monkeypatch.setattr("nubor.core.config.openstack.connect", fake_connect)
    return calls


def test_explicit_cloud_wins_over_active_configuration(monkeypatch):
    calls = _capture_connect(monkeypatch)
    config.set_active_configuration("stored")
    assert config.connect("explicit") == "conn"
    assert calls["kwargs"] == {"cloud": "explicit"}


def test_active_configuration_used_when_no_override(monkeypatch):
    calls = _capture_connect(monkeypatch)
    config.set_active_configuration("stored")
    config.connect()
    assert calls["kwargs"] == {"cloud": "stored"}


def test_sdk_defaults_used_when_nothing_configured(monkeypatch):
    calls = _capture_connect(monkeypatch)
    config.connect()
    assert calls["kwargs"] == {}


def test_connect_failure_exits_1_with_hint(monkeypatch, capsys):
    def boom(**kwargs):
        raise RuntimeError("no auth")

    monkeypatch.setattr("nubor.core.config.openstack.connect", boom)
    with pytest.raises(SystemExit) as excinfo:
        config.connect()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "could not connect" in err
    assert "clouds.yaml" in err
