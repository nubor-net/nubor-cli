from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from click.testing import CliRunner

from nubor.cli import main


def _named_mock(name, **attrs):
    m = mock.MagicMock()
    m.name = name
    for key, value in attrs.items():
        setattr(m, key, value)
    return m


def test_clusters_list(fake_conn):
    fake_conn.container_infrastructure_management.clusters.return_value = [
        SimpleNamespace(
            name="prod", status="CREATE_COMPLETE", node_count=3, master_count=1, keypair="k"
        )
    ]
    result = CliRunner().invoke(main, ["container", "clusters", "list"])
    assert result.exit_code == 0
    assert "prod" in result.output
    assert "CREATE_COMPLETE" in result.output


def test_clusters_create_quiet_passes_template_id(fake_conn):
    template = _named_mock("k8s-tpl", uuid="t-1")
    fake_conn.container_infrastructure_management.find_cluster_template.return_value = template
    fake_conn.container_infrastructure_management.create_cluster.return_value = _named_mock(
        "prod", uuid="c-1"
    )
    result = CliRunner().invoke(
        main,
        [
            "container",
            "clusters",
            "create",
            "prod",
            "--cluster-template",
            "k8s-tpl",
            "--node-count",
            "3",
            "-q",
        ],
    )
    assert result.exit_code == 0
    fake_conn.container_infrastructure_management.create_cluster.assert_called_once_with(
        name="prod", cluster_template_id="t-1", node_count=3, master_count=1
    )


def test_clusters_delete_declined_makes_no_api_call(fake_conn):
    fake_conn.container_infrastructure_management.find_cluster.return_value = _named_mock(
        "prod", uuid="c-1", status="CREATE_COMPLETE"
    )
    result = CliRunner().invoke(main, ["container", "clusters", "delete", "prod"], input="n\n")
    assert result.exit_code == 1
    fake_conn.container_infrastructure_management.delete_cluster.assert_not_called()


def test_clusters_resize_quiet_calls_magnum_resource_action(fake_conn):
    cluster = _named_mock("prod", uuid="c-1", status="UPDATE_COMPLETE", node_count=3)
    fake_conn.container_infrastructure_management.find_cluster.return_value = cluster

    result = CliRunner().invoke(main, ["container", "clusters", "resize", "prod", "4", "-q"])

    assert result.exit_code == 0
    cluster.resize.assert_called_once_with(
        fake_conn.container_infrastructure_management, node_count=4
    )
