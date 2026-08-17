from __future__ import annotations

from types import SimpleNamespace

from click.testing import CliRunner

from nubor.cli import main


def test_activate_writes_state_file(isolated_state):
    result = CliRunner().invoke(main, ["config", "configurations", "activate", "prod"])
    assert result.exit_code == 0
    assert (isolated_state / "active_configuration").read_text() == "prod"


def test_list_marks_the_active_configuration(isolated_state, monkeypatch):
    fake_loader = SimpleNamespace(cloud_config={"clouds": {"prod": {}, "lab": {}}})
    monkeypatch.setattr("openstack.config.loader.OpenStackConfig", lambda: fake_loader)
    (isolated_state / "active_configuration").write_text("lab")
    result = CliRunner().invoke(main, ["config", "configurations", "list"])
    assert result.exit_code == 0
    assert "prod" in result.output
    assert "lab" in result.output
    assert "True" in result.output  # lab is marked active


def test_auth_list_reports_active_configuration(isolated_state):
    (isolated_state / "active_configuration").write_text("lab")
    result = CliRunner().invoke(main, ["auth", "list"])
    assert result.exit_code == 0
    assert "lab" in result.output
