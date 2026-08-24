from __future__ import annotations

from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Keep every test away from the real ~/.config/nubor."""
    import nubor.core.config as config

    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "ACTIVE_CONFIG_FILE", tmp_path / "active_configuration")
    monkeypatch.setattr(config, "_validate_private_connection", lambda conn: conn)
    monkeypatch.setenv("NUBOR_DIRECT", "1")
    return tmp_path


@pytest.fixture
def fake_conn(monkeypatch):
    """A mock connection wired into connect(); no test touches a network."""
    conn = mock.MagicMock()
    monkeypatch.setattr("nubor.core.config.openstack.connect", lambda **kwargs: conn)
    return conn
