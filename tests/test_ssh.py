from __future__ import annotations

import time
from types import SimpleNamespace
from unittest import mock

from click.testing import CliRunner

from nubor.cli import main
from nubor.core import ssh

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFAKEKEYFAKEKEYFAKEKEYFAKEKEYFAKEKEYFA"


def _server(**attrs):
    defaults = {
        "id": "srv-1",
        "name": "web-1",
        "status": "ACTIVE",
        "key_name": None,
        "metadata": {},
        "image": {"id": "img-1"},
        "addresses": {"net": [{"addr": "10.0.0.5", "OS-EXT-IPS:type": "fixed"}]},
    }
    return SimpleNamespace(**{**defaults, **attrs})


def _image(name="ubuntu-24.04", os_admin_user=None, os_distro=None, properties=None):
    return SimpleNamespace(
        id="img-1",
        name=name,
        os_admin_user=os_admin_user,
        os_distro=os_distro,
        properties=properties or {},
    )


def _wire(fake_conn, server=None, image=None):
    server = server or _server()
    fake_conn.compute.find_server.return_value = server
    fake_conn.compute.get_server.return_value = server
    fake_conn.image.find_image.return_value = image if image is not None else _image()
    return server


# --------------------------------------------------------------------------
# address and login user
# --------------------------------------------------------------------------
def test_pick_address_prefers_the_floating_ip():
    server = _server(
        addresses={
            "net": [
                {"addr": "10.0.0.5", "OS-EXT-IPS:type": "fixed"},
                {"addr": "172.24.4.9", "OS-EXT-IPS:type": "floating"},
            ]
        }
    )
    assert ssh.pick_address(server, internal=False) == "172.24.4.9"
    assert ssh.pick_address(server, internal=True) == "10.0.0.5"


def test_pick_address_falls_back_to_fixed_when_there_is_no_floating_ip():
    assert ssh.pick_address(_server(), internal=False) == "10.0.0.5"
    assert ssh.pick_address(_server(addresses={}), internal=False) is None


def test_login_user_precedence(fake_conn):
    """Server metadata beats the image property, which beats a name guess."""
    image = _image(name="ubuntu-24.04", os_admin_user="cloud-user")

    server = _server(metadata={"ssh_user": "declared"})
    assert ssh.resolve_user(fake_conn, server)[0] == "declared"

    fake_conn.image.find_image.return_value = image
    assert ssh.resolve_user(fake_conn, _server())[0] == "cloud-user"

    fake_conn.image.find_image.return_value = _image(name="ubuntu-24.04")
    user, source = ssh.resolve_user(fake_conn, _server())
    assert user == "ubuntu" and "guessed" in source


def test_guess_user_uses_os_distro_when_the_name_is_opaque():
    assert ssh.guess_user("golden-image-07", "ubuntu") == "ubuntu"
    assert ssh.guess_user("RHEL9", None) == "cloud-user"
    assert ssh.guess_user("golden-image-07", None) is None


def test_ssh_without_a_declared_user_is_a_clean_error(fake_conn):
    _wire(fake_conn, image=_image(name="golden-image-07"))
    result = CliRunner().invoke(main, ["compute", "instances", "ssh", "web-1", "--dry-run"])
    assert result.exit_code == 1
    assert "nothing declares a login user" in result.output
    assert "os_admin_user" in result.output


# --------------------------------------------------------------------------
# the ssh command line
# --------------------------------------------------------------------------
def test_dry_run_builds_the_command_and_runs_nothing(fake_conn):
    _wire(fake_conn)
    with mock.patch("subprocess.call") as called:
        result = CliRunner().invoke(
            main, ["compute", "instances", "ssh", "web-1", "--dry-run", "--user", "ubuntu"]
        )
    assert result.exit_code == 0
    assert "ssh ubuntu@10.0.0.5" in result.output
    called.assert_not_called()


def test_extra_args_are_passed_through_untouched(fake_conn):
    _wire(fake_conn)
    result = CliRunner().invoke(
        main,
        [
            "compute",
            "instances",
            "ssh",
            "web-1",
            "--dry-run",
            "--user",
            "ubuntu",
            "--",
            "-L",
            "8080:localhost:80",
            "uptime",
        ],
    )
    assert "ssh ubuntu@10.0.0.5 -L 8080:localhost:80 uptime" in result.output


def test_tunnel_through_becomes_proxyjump(fake_conn):
    _wire(fake_conn)
    result = CliRunner().invoke(
        main,
        [
            "compute",
            "instances",
            "ssh",
            "web-1",
            "--dry-run",
            "--user",
            "ubuntu",
            "--tunnel-through",
            "bastion.example",
        ],
    )
    assert "-J bastion.example" in result.output


def test_proxy_command_expands_the_instance_name(fake_conn):
    _wire(fake_conn)
    result = CliRunner().invoke(
        main,
        [
            "compute",
            "instances",
            "ssh",
            "web-1",
            "--dry-run",
            "--user",
            "ubuntu",
            "--proxy-command",
            "cloudflared access ssh --hostname {instance}.ssh.example.net",
        ],
    )
    assert "ProxyCommand=cloudflared access ssh --hostname web-1.ssh.example.net" in result.output


def test_tunnel_and_proxy_together_are_refused(fake_conn):
    _wire(fake_conn)
    result = CliRunner().invoke(
        main,
        [
            "compute",
            "instances",
            "ssh",
            "web-1",
            "--dry-run",
            "--user",
            "ubuntu",
            "--tunnel-through",
            "host",
            "--proxy-command",
            "cmd",
        ],
    )
    assert result.exit_code == 1
    assert "alternatives" in result.output


# --------------------------------------------------------------------------
# reachability
# --------------------------------------------------------------------------
def test_unreachable_address_is_reported_as_such_and_injects_nothing(fake_conn, monkeypatch):
    """The failure must not be blamed on the guest agent, and must not leave an
    unusable key behind in the instance's metadata."""
    _wire(fake_conn, image=_image(os_admin_user="ubuntu", properties={"nubor_agent": "true"}))
    monkeypatch.setattr(ssh, "wait_for_port", lambda *a, **k: False)
    result = CliRunner().invoke(main, ["compute", "instances", "ssh", "web-1"])
    assert result.exit_code == 1
    assert "nothing is answering on 10.0.0.5:22" in result.output
    fake_conn.compute.set_server_metadata.assert_not_called()


def test_falls_back_to_a_saved_proxy_when_there_is_no_direct_route(fake_conn, monkeypatch):
    _wire(fake_conn)
    ssh.save_proxy_command("cloudflared access ssh --hostname {instance}.ssh.example.net")
    wait = mock.Mock(return_value=False)
    monkeypatch.setattr(ssh, "wait_for_port", wait)
    with mock.patch("subprocess.call", return_value=0) as called:
        CliRunner().invoke(main, ["compute", "instances", "ssh", "web-1", "--user", "ubuntu"])
    wait.assert_called_once_with("10.0.0.5", attempts=1, delay=1)
    assert "ProxyCommand=cloudflared access ssh --hostname web-1.ssh.example.net" in (
        " ".join(called.call_args[0][0])
    )


def test_a_reachable_address_ignores_the_saved_proxy(fake_conn, monkeypatch):
    _wire(fake_conn)
    ssh.save_proxy_command("cloudflared access ssh --hostname {instance}.ssh.example.net")
    monkeypatch.setattr(ssh, "wait_for_port", lambda *a, **k: True)
    with mock.patch("subprocess.call", return_value=0) as called:
        CliRunner().invoke(main, ["compute", "instances", "ssh", "web-1", "--user", "ubuntu"])
    assert "ProxyCommand" not in " ".join(called.call_args[0][0])


def test_internal_address_uses_the_saved_proxy_without_a_route_probe(fake_conn, monkeypatch):
    _wire(fake_conn)
    ssh.save_proxy_command("proxy %h %p")
    wait = mock.Mock()
    monkeypatch.setattr(ssh, "wait_for_port", wait)
    with mock.patch("subprocess.call", return_value=0) as called:
        CliRunner().invoke(
            main,
            ["compute", "instances", "ssh", "web-1", "--user", "ubuntu", "--internal-ip"],
        )
    wait.assert_not_called()
    assert "ProxyCommand=proxy %h %p" in " ".join(called.call_args[0][0])


def test_ssh_proxy_save_show_and_clear():
    runner = CliRunner()
    assert "(none saved)" in runner.invoke(main, ["compute", "instances", "ssh-proxy"]).output
    runner.invoke(main, ["compute", "instances", "ssh-proxy", "some proxy {instance}"])
    assert (
        "some proxy {instance}" in runner.invoke(main, ["compute", "instances", "ssh-proxy"]).output
    )
    runner.invoke(main, ["compute", "instances", "ssh-proxy", "--clear"])
    assert "(none saved)" in runner.invoke(main, ["compute", "instances", "ssh-proxy"]).output


# --------------------------------------------------------------------------
# ephemeral keys
# --------------------------------------------------------------------------
def test_agent_present_reads_the_instance_before_the_image(fake_conn):
    fake_conn.image.find_image.return_value = _image()
    assert ssh.agent_present(fake_conn, _server(metadata={"nubor_agent": "true"})) is True
    assert ssh.agent_present(fake_conn, _server()) is False
    fake_conn.image.find_image.return_value = _image(properties={"nubor_agent": "true"})
    assert ssh.agent_present(fake_conn, _server()) is True


def test_injected_key_fits_nova_metadata_and_is_revoked_on_exit(fake_conn, monkeypatch, tmp_path):
    image = _image(os_admin_user="ubuntu", properties={"nubor_agent": "true"})
    server = _wire(fake_conn, image=image)
    monkeypatch.setattr(ssh, "wait_for_port", lambda *a, **k: True)
    monkeypatch.setattr(ssh, "wait_for_key", lambda *a, **k: True)
    monkeypatch.setattr(ssh, "mint_ephemeral_key", lambda d: (str(tmp_path / "k"), KEY))

    with mock.patch("subprocess.call", return_value=0):
        CliRunner().invoke(main, ["compute", "instances", "ssh", "web-1"])

    name, value = next(iter(fake_conn.compute.set_server_metadata.call_args.kwargs.items()))
    assert name.startswith("nubor_ssh_")
    assert len(value) <= ssh.NOVA_METADATA_VALUE_LIMIT
    user, expiry, key = value.split(":", 2)
    assert user == "ubuntu" and key == KEY and int(expiry) > time.time()
    fake_conn.compute.delete_server_metadata.assert_called_once_with(server, [name])


def test_key_is_revoked_even_when_the_agent_never_accepts_it(fake_conn, monkeypatch, tmp_path):
    _wire(fake_conn, image=_image(os_admin_user="ubuntu", properties={"nubor_agent": "true"}))
    monkeypatch.setattr(ssh, "wait_for_port", lambda *a, **k: True)
    monkeypatch.setattr(ssh, "wait_for_key", lambda *a, **k: False)
    monkeypatch.setattr(ssh, "mint_ephemeral_key", lambda d: (str(tmp_path / "k"), KEY))

    result = CliRunner().invoke(main, ["compute", "instances", "ssh", "web-1"])
    assert result.exit_code == 1
    assert "never accepted the key" in result.output
    fake_conn.compute.delete_server_metadata.assert_called_once()


def test_no_agent_marker_means_no_injection(fake_conn, monkeypatch):
    _wire(fake_conn, image=_image(os_admin_user="ubuntu"))
    monkeypatch.setattr(ssh, "wait_for_port", lambda *a, **k: True)
    with mock.patch("subprocess.call", return_value=0):
        CliRunner().invoke(main, ["compute", "instances", "ssh", "web-1"])
    fake_conn.compute.set_server_metadata.assert_not_called()


def test_minted_key_is_accepted_by_the_guest_agent(tmp_path):
    """The CLI and guest/nubor-ssh-agent agree on the metadata format.

    These two halves ship in one repo but run on different machines, so nothing
    else would catch the day one side changes the layout.
    """
    agent = _load_guest_agent()
    _, public_key = ssh.mint_ephemeral_key(str(tmp_path))
    captured: dict[str, str] = {}
    conn = mock.MagicMock()
    conn.compute.set_server_metadata.side_effect = lambda server, **kw: captured.update(kw)

    name = ssh.inject_key(conn, _server(), "ubuntu", public_key, 300)
    value = captured[name]
    assert len(value) <= ssh.NOVA_METADATA_VALUE_LIMIT
    with mock.patch.object(agent, "pwd", mock.MagicMock()):
        assert agent.parse_entries({name: value}, int(time.time())) == {"ubuntu": [public_key]}


def _load_guest_agent():
    """Import guest/nubor-ssh-agent, which has no .py suffix and imports pwd."""
    import importlib.machinery
    import importlib.util
    import pathlib
    import sys
    import types

    sys.modules.setdefault("pwd", types.SimpleNamespace(getpwnam=lambda name: None))
    path = pathlib.Path(__file__).resolve().parent.parent / "guest" / "nubor-ssh-agent"
    loader = importlib.machinery.SourceFileLoader("nubor_ssh_agent", str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# images
# --------------------------------------------------------------------------
def test_images_list_hides_images_without_the_agent(fake_conn):
    fake_conn.image.images.return_value = [
        _image(name="ubuntu-agent", properties={"nubor_agent": "true"}),
        _image(name="plain-image"),
    ]
    for i in fake_conn.image.images.return_value:
        i.status, i.size, i.visibility = "active", 1, "public"

    listed = CliRunner().invoke(main, ["compute", "images", "list"]).output
    assert "ubuntu-agent" in listed and "plain-image" not in listed

    everything = CliRunner().invoke(main, ["compute", "images", "list", "--all"]).output
    assert "ubuntu-agent" in everything and "plain-image" in everything


def test_prune_dry_run_deletes_nothing_and_spares_protected_and_in_use(fake_conn):
    doomed = _image(name="stale")
    doomed.id = "img-stale"
    protected = _image(name="amphora-x64-haproxy", properties={"nubor_keep": "true"})
    in_use = _image(name="booted")
    in_use.id = "img-booted"
    fake_conn.image.images.return_value = [doomed, protected, in_use]
    fake_conn.compute.servers.return_value = [SimpleNamespace(image={"id": "img-booted"})]

    result = CliRunner().invoke(main, ["compute", "images", "prune", "--dry-run"])
    assert "delete stale" in result.output
    assert "skip   booted" in result.output
    assert "amphora-x64-haproxy" not in result.output
    assert "1 image(s) would be deleted" in result.output
    fake_conn.image.delete_image.assert_not_called()


def test_prune_declined_makes_no_api_call(fake_conn):
    doomed = _image(name="stale")
    doomed.id = "img-stale"
    fake_conn.image.images.return_value = [doomed]
    fake_conn.compute.servers.return_value = []

    result = CliRunner().invoke(main, ["compute", "images", "prune"], input="n\n")
    assert result.exit_code == 1
    fake_conn.image.delete_image.assert_not_called()


def test_prune_refuses_when_it_cannot_see_across_projects(fake_conn):
    import openstack.exceptions

    doomed = _image(name="stale")
    doomed.id = "img-stale"
    fake_conn.image.images.return_value = [doomed]
    fake_conn.compute.servers.side_effect = openstack.exceptions.HttpException("403")

    result = CliRunner().invoke(main, ["compute", "images", "prune", "--quiet"])
    assert result.exit_code == 1
    assert "unknowable" in result.output
    fake_conn.image.delete_image.assert_not_called()


def test_ssh_refuses_an_instance_that_is_not_running(fake_conn):
    _wire(fake_conn, _server(status="SHUTOFF"))

    result = CliRunner().invoke(main, ["compute", "instances", "ssh", "web-1"])

    assert result.exit_code == 1
    assert "is SHUTOFF, not ACTIVE" in result.output
    assert "instances start web-1" in result.output
    fake_conn.compute.set_server_metadata.assert_not_called()


def test_ssh_does_not_claim_reachability_it_never_checked(fake_conn, monkeypatch):
    """--internal-ip with a proxy skips the port probe, so a failed login is
    not evidence about the guest agent one way or the other."""
    _wire(fake_conn, _server(metadata={"nubor_agent": "true"}))
    monkeypatch.setattr(ssh, "wait_for_key", lambda *a, **k: False)
    monkeypatch.setattr(
        ssh, "wait_for_port", lambda *a, **k: (_ for _ in ()).throw(AssertionError("probed"))
    )

    result = CliRunner().invoke(
        main,
        [
            "compute",
            "instances",
            "ssh",
            "web-1",
            "--internal-ip",
            "--proxy-command",
            "nc %h %p",
        ],
    )

    assert result.exit_code == 1
    assert "could not log in to web-1 through the proxy command" in result.output
    assert "does not reach 10.0.0.5:22" in result.output
    assert "nubor-ssh-agent" in result.output
    assert "never accepted the key" not in result.output
