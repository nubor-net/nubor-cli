from __future__ import annotations

import json

from click.testing import CliRunner

from nubor import __version__
from nubor.cli import main


def test_components_list(monkeypatch) -> None:
    monkeypatch.setattr("nubor.commands.components._latest_version", lambda: "9.8.7")
    result = CliRunner().invoke(main, ["components", "list", "--format", "json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == [
        {
            "status": "Update Available",
            "name": "nubor CLI core",
            "id": "nubor",
            "installed_version": __version__,
            "latest_version": "9.8.7",
        }
    ]


def test_components_list_local_state_never_calls_network(monkeypatch) -> None:
    def latest() -> str:
        raise AssertionError("network called")

    monkeypatch.setattr("nubor.commands.components._latest_version", latest)
    result = CliRunner().invoke(main, ["components", "list", "--only-local-state"])

    assert result.exit_code == 0
    assert "nubor CLI core" in result.output
    assert "unknown" in result.output


def test_components_update_skips_current_version(monkeypatch) -> None:
    def run(version: str) -> None:
        raise AssertionError(f"installer called for {version}")

    monkeypatch.setattr("nubor.commands.components._run_installer", run)

    result = CliRunner().invoke(main, ["components", "update", "--version", __version__])

    assert result.exit_code == 0
    assert "All components are up to date" in result.output


def test_components_update_runs_confirmed_version(monkeypatch) -> None:
    installed: list[str] = []
    monkeypatch.setattr("nubor.commands.components._run_installer", installed.append)

    result = CliRunner().invoke(main, ["components", "update", "--version", "9.8.7", "--quiet"])

    assert result.exit_code == 0
    assert installed == ["9.8.7"]
    assert "Updated nubor to 9.8.7" in result.output


def test_components_update_rejects_invalid_version() -> None:
    result = CliRunner().invoke(main, ["components", "update", "--version", "../../bad", "--quiet"])

    assert result.exit_code == 1
    assert "invalid version" in result.output
