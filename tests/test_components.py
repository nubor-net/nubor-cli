from __future__ import annotations

import json

from click.testing import CliRunner

from nubor import __version__
from nubor.cli import main


def test_components_list() -> None:
    result = CliRunner().invoke(main, ["components", "list", "--format", "json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == [
        {"component": "nubor", "version": __version__, "status": "installed"}
    ]


def test_components_update_skips_current_version(monkeypatch) -> None:
    def run(version: str) -> None:
        raise AssertionError(f"installer called for {version}")

    monkeypatch.setattr("nubor.commands.components._run_installer", run)

    result = CliRunner().invoke(main, ["components", "update", "--version", __version__])

    assert result.exit_code == 0
    assert "already up to date" in result.output


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
