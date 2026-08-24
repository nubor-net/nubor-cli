from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import mock

from click.testing import CliRunner

from nubor import __version__
from nubor.cli import main
from nubor.commands import components


def test_components_list(monkeypatch) -> None:
    monkeypatch.setattr("nubor.commands.components._latest_version", lambda: "9.8.7")
    monkeypatch.setattr("nubor.commands.components._service_rows", list)
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


def _endpoint(api_version, min_micro=None, max_micro=None):
    return SimpleNamespace(
        api_version=api_version, min_microversion=min_micro, max_microversion=max_micro
    )


def test_api_rows_report_compatibility_per_service(monkeypatch) -> None:
    monkeypatch.setattr("nubor.core.config.direct_mode", lambda: True)
    conn = mock.MagicMock()
    conn.identity.get_endpoint_data.return_value = _endpoint((3, 14))
    conn.compute.get_endpoint_data.return_value = _endpoint((2, 1), (2, 1), (2, 103))
    # A cloud that has moved its floor above what nubor calls is as broken as
    # one that is too old, and updating nubor is not what fixes either.
    conn.image.get_endpoint_data.return_value = _endpoint((1, 0))
    conn.block_storage.get_endpoint_data.return_value = _endpoint((3, 0), (3, 40), (3, 71))
    conn.network.get_endpoint_data.side_effect = RuntimeError("endpoint not in the catalog")
    conn.container_infrastructure_management.get_endpoint_data.return_value = _endpoint((1, 0))
    monkeypatch.setattr("nubor.core.config.connect", lambda *a, **k: conn)

    rows = {row["id"]: row for row in components._service_rows()}

    assert rows["identity"]["status"] == "Compatible"
    assert rows["compute"]["installed_version"] == "2.103"
    assert rows["image"]["status"] == "Incompatible"
    assert rows["block-storage"]["status"] == "Incompatible"
    assert rows["network"]["status"] == "Unknown"
    assert rows["network"]["latest_version"] == "needs 2.0+"


def test_api_rows_do_not_touch_the_cloud_behind_the_gateway(monkeypatch) -> None:
    monkeypatch.setattr("nubor.core.config.direct_mode", lambda: False)

    def connect(*_args, **_kwargs):
        raise AssertionError("connected while behind api.nubor.net")

    monkeypatch.setattr("nubor.core.config.connect", connect)

    rows = components._service_rows()

    assert {row["status"] for row in rows} == {"Unknown"}
    assert all(row["installed_version"] == "via api.nubor.net" for row in rows)


def test_components_list_includes_the_service_rows(monkeypatch) -> None:
    monkeypatch.setattr("nubor.commands.components._latest_version", lambda: __version__)
    monkeypatch.setattr("nubor.core.config.direct_mode", lambda: False)

    result = CliRunner().invoke(main, ["components", "list"])

    assert result.exit_code == 0
    assert "Nova (compute)" in result.output
    assert "Magnum (container infra)" in result.output


def test_components_list_local_state_leaves_the_services_out(monkeypatch) -> None:
    result = CliRunner().invoke(main, ["components", "list", "--only-local-state"])

    assert result.exit_code == 0
    assert "Nova (compute)" not in result.output
