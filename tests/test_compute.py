from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import openstack.exceptions
from click.testing import CliRunner

from nubor.cli import main


def _server(name="probe"):
    return SimpleNamespace(
        name=name,
        status="ACTIVE",
        flavor={"original_name": "m1.tiny"},
        image={"id": "img-1"},
        addresses={"net": [{"addr": "10.0.0.5"}]},
    )


def _named_mock(name, **attrs):
    m = mock.MagicMock()
    m.name = name  # MagicMock(name=...) names the mock itself, not the attribute
    for key, value in attrs.items():
        setattr(m, key, value)
    return m


def test_instances_list(fake_conn):
    fake_conn.compute.servers.return_value = [_server()]
    result = CliRunner().invoke(main, ["compute", "instances", "list"])
    assert result.exit_code == 0
    assert "probe" in result.output
    assert "m1.tiny" in result.output
    assert "10.0.0.5" in result.output


def test_instances_describe_not_found_is_a_clean_error(fake_conn):
    fake_conn.compute.find_server.side_effect = openstack.exceptions.NotFoundException("gone")
    result = CliRunner().invoke(main, ["compute", "instances", "describe", "nope"])
    assert result.exit_code == 1
    assert "no instance found matching 'nope'" in result.output
    assert "Traceback" not in result.output


def test_instances_delete_declined_makes_no_api_call(fake_conn):
    fake_conn.compute.find_server.return_value = _named_mock("probe", id="s-1", status="ACTIVE")
    result = CliRunner().invoke(main, ["compute", "instances", "delete", "probe"], input="n\n")
    assert result.exit_code == 1
    fake_conn.compute.delete_server.assert_not_called()


def test_instances_delete_quiet_skips_prompt(fake_conn):
    server = _named_mock("probe", id="s-1", status="ACTIVE")
    fake_conn.compute.find_server.return_value = server
    result = CliRunner().invoke(main, ["compute", "instances", "delete", "probe", "-q"])
    assert result.exit_code == 0
    fake_conn.compute.delete_server.assert_called_once_with(server)


def test_instances_create_resolves_and_confirms(fake_conn):
    fake_conn.compute.find_flavor.return_value = _named_mock("m1.tiny", id="f-1")
    fake_conn.image.find_image.return_value = _named_mock("ubuntu", id="i-1")
    fake_conn.network.find_network.return_value = _named_mock("lan", id="n-1")
    fake_conn.compute.create_server.return_value = _named_mock("vm1", id="s-9", status="BUILD")
    result = CliRunner().invoke(
        main,
        [
            "compute",
            "instances",
            "create",
            "vm1",
            "--flavor",
            "m1.tiny",
            "--image",
            "ubuntu",
            "--network",
            "lan",
        ],
        input="y\n",
    )
    assert result.exit_code == 0
    assert "m1.tiny" in result.output  # the prompt shows what was resolved
    fake_conn.compute.create_server.assert_called_once_with(
        name="vm1",
        flavor_id="f-1",
        image_id="i-1",
        networks=[{"uuid": "n-1"}],
    )


def test_instances_create_declined_makes_no_api_call(fake_conn):
    fake_conn.compute.find_flavor.return_value = _named_mock("m1.tiny", id="f-1")
    fake_conn.image.find_image.return_value = _named_mock("ubuntu", id="i-1")
    fake_conn.network.find_network.return_value = _named_mock("lan", id="n-1")
    result = CliRunner().invoke(
        main,
        [
            "compute",
            "instances",
            "create",
            "vm1",
            "--flavor",
            "m1.tiny",
            "--image",
            "ubuntu",
            "--network",
            "lan",
        ],
        input="n\n",
    )
    assert result.exit_code == 1
    fake_conn.compute.create_server.assert_not_called()


def test_disks_create_quiet(fake_conn):
    fake_conn.block_storage.create_volume.return_value = _named_mock(
        "d1", id="v-1", status="creating"
    )
    result = CliRunner().invoke(main, ["compute", "disks", "create", "d1", "--size", "1", "-q"])
    assert result.exit_code == 0
    fake_conn.block_storage.create_volume.assert_called_once_with(name="d1", size=1)


def test_disks_delete_declined_makes_no_api_call(fake_conn):
    fake_conn.block_storage.find_volume.return_value = _named_mock(
        "d1", id="v-1", size=1, status="available"
    )
    result = CliRunner().invoke(main, ["compute", "disks", "delete", "d1"], input="n\n")
    assert result.exit_code == 1
    fake_conn.block_storage.delete_volume.assert_not_called()


def test_images_list(fake_conn):
    fake_conn.image.images.return_value = [
        SimpleNamespace(name="ubuntu", status="active", size=1024, visibility="public")
    ]
    result = CliRunner().invoke(main, ["compute", "images", "list"])
    assert result.exit_code == 0
    assert "ubuntu" in result.output
