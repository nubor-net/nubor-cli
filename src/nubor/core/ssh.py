"""Reaching an instance over SSH, and the short-lived keys that make it work.

Nova can tell us an instance's address. It cannot tell us the login user - the
keypair is baked in at boot by cloud-init and the account it lands in is an
image convention - and it has no way to hand a running instance a new key.

`guest/nubor-ssh-agent` supplies the missing half: installed in the image, it
watches the metadata service and maintains a managed block in a user's
authorized_keys. That is what lets `nubor compute instances ssh` mint a key per
session and revoke it on the way out, instead of relying on a long-lived
keypair.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from typing import Any

import click

from nubor.core import config

# Where the login user comes from, most authoritative first:
#   1. server metadata "ssh_user" - per-instance, settable on a running server.
#   2. the image's os_admin_user property - a STANDARD Glance field meant for
#      exactly this. Populate it once per image and every tool benefits:
#          openstack image set --property os_admin_user=ubuntu <image>
#   3. the image name / os_distro, guessed below.
# --user beats all three.
IMAGE_DEFAULT_USERS = {
    "ubuntu": "ubuntu",
    "debian": "debian",
    "centos": "centos",
    "rocky": "rocky",
    "alma": "almalinux",
    "fedora": "fedora",
    "rhel": "cloud-user",
    "cirros": "cirros",
    "coreos": "core",
    "opensuse": "opensuse",
}

# Nova caps a metadata value at 255 characters. An ed25519 public key is ~80,
# leaving room for the user and expiry - an RSA key would not fit, which is why
# the key type below is not configurable.
NOVA_METADATA_VALUE_LIMIT = 255
EPHEMERAL_METADATA_PREFIX = "nubor_ssh_"

EXAMPLE_PROXY_COMMAND = "cloudflared access ssh --hostname {instance}.ssh.example.net"

TRUTHY = ("true", "1", "yes")


def _proxy_file():
    """Resolved on each call rather than at import: tests point STATE_DIR at a
    temporary directory, and a module-level constant would miss that."""
    return config.STATE_DIR / "ssh_proxy"


def saved_proxy_command() -> str | None:
    """The standing proxy command, if one was saved. One line in
    ~/.config/nubor, the same shape as the active configuration."""
    path = _proxy_file()
    if path.exists():
        return path.read_text().strip() or None
    return None


def save_proxy_command(command: str) -> None:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    _proxy_file().write_text(command)


def clear_proxy_command() -> None:
    _proxy_file().unlink(missing_ok=True)


def _is_true(value: Any) -> bool:
    return str(value or "").lower() in TRUTHY


def _image_property(image: Any, name: str) -> Any:
    # getattr rather than image.properties: a Glance image always has the
    # attribute, but a partial record from another call may not, and an image
    # listing should never blow up over a missing optional field.
    return (getattr(image, "properties", None) or {}).get(name)


def has_agent_property(image: Any) -> bool:
    """True when an image is marked as carrying guest/nubor-ssh-agent."""
    return _is_true(_image_property(image, "nubor_agent"))


def is_protected(image: Any) -> bool:
    """nubor_keep=true means 'never prune this', for images that will never
    carry the agent by design - Octavia amphorae, Trove guests, Manila service
    images, Magnum node images. Those are built by their own pipelines and the
    cloud breaks without them.
    """
    return _is_true(_image_property(image, "nubor_keep"))


def _server_image_id(server: Any) -> str | None:
    image = server.image
    return image.get("id") if isinstance(image, dict) else None


def agent_present(conn: Any, server: Any) -> bool:
    """True when the instance is marked as carrying the agent.

    Set per instance by the terraform compute module (which installs the agent
    via cloud-init), or once per image at build time:
        openstack image set --property nubor_agent=true <image>
    Without the agent nothing inside the VM ever reads an injected key, so
    guessing wrong here would mean a confident-looking hang.
    """
    if _is_true((server.metadata or {}).get("nubor_agent")):
        return True
    image_id = _server_image_id(server)
    if not image_id:
        return False
    image = conn.image.find_image(image_id)
    return bool(image) and has_agent_property(image)


def guess_user(*hints: str | None) -> str | None:
    """First image name / os_distro hint that matches a known distro."""
    for hint in hints:
        lowered = (hint or "").lower()
        for token, user in IMAGE_DEFAULT_USERS.items():
            if token in lowered:
                return user
    return None


def resolve_user(conn: Any, server: Any) -> tuple[str | None, str | None]:
    """(user, where it came from), or (None, None) if nothing declares one."""
    declared = (server.metadata or {}).get("ssh_user")
    if declared:
        return declared, "server metadata ssh_user"

    image_id = _server_image_id(server)
    image = conn.image.find_image(image_id) if image_id else None
    if image is None:
        return None, None
    if image.os_admin_user:
        return image.os_admin_user, "image property os_admin_user"

    guessed = guess_user(image.name, image.os_distro)
    return (guessed, f"guessed from image '{image.name}'") if guessed else (None, None)


def pick_address(server: Any, internal: bool) -> str | None:
    """The floating IP by default - that is the one reachable from here - or the
    fixed IP with --internal-ip. Both live in server.addresses, tagged by Nova.
    """
    fixed: list[str] = []
    floating: list[str] = []
    for entries in (server.addresses or {}).values():
        for entry in entries:
            addr = entry.get("addr")
            if not addr:
                continue
            target = floating if entry.get("OS-EXT-IPS:type") == "floating" else fixed
            target.append(addr)
    if internal:
        return fixed[0] if fixed else None
    return (floating or fixed or [None])[0]


def mint_ephemeral_key(directory: str) -> tuple[str, str]:
    """An ed25519 keypair that lives and dies with one command. Returns
    (private key path, public key text)."""
    path = os.path.join(directory, "nubor-ephemeral")
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", path, "-C", "nubor-ephemeral"],
        check=True,
    )
    with open(path + ".pub") as handle:
        # Drop the comment: the agent only writes type + blob anyway.
        return path, " ".join(handle.read().split()[:2])


def inject_key(conn: Any, server: Any, user: str, public_key: str, ttl: int) -> str:
    """Publish the key in server metadata for the in-guest agent. Returns the
    metadata key so the caller can revoke it."""
    expiry = int(time.time()) + ttl
    value = f"{user}:{expiry}:{public_key}"
    if len(value) > NOVA_METADATA_VALUE_LIMIT:
        click.echo("error: ephemeral key does not fit in Nova metadata", err=True)
        sys.exit(1)
    # The suffix keeps concurrent sessions - or two of your own terminals - from
    # overwriting each other's slot; the agent drops each one at its expiry.
    suffix = public_key.split()[1][-8:].replace("/", "_").replace("+", "_")
    name = EPHEMERAL_METADATA_PREFIX + suffix
    conn.compute.set_server_metadata(server, **{name: value})
    return name


def wait_for_port(host: str, port: int = 22, attempts: int = 12, delay: int = 5) -> bool:
    """True once something answers on host:port.

    Separating this from the key check is what stops the command blaming the
    guest agent for what is really an unreachable address - a floating IP that
    is not plumbed, or a security group that does not allow 22, both of which
    look identical to a failed login otherwise.
    """
    for attempt in range(attempts):
        sock = socket.socket()
        sock.settimeout(delay)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            if attempt == 0:
                click.echo(f"# waiting for {host}:{port}...", err=True)
            if attempt + 1 < attempts:
                time.sleep(delay)
        finally:
            sock.close()
    return False


def wait_for_key(cmd: list[str], attempts: int = 7, delay: int = 2) -> bool:
    """Poll until the guest agent has picked the key up; it polls on its own
    schedule, so the first attempt usually fails."""
    probe = [cmd[0], "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", *cmd[1:], "true"]
    for attempt in range(attempts):
        if subprocess.call(probe, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
            return True
        if attempt == 0:
            click.echo("# waiting for the guest agent to pick up the key...", err=True)
        time.sleep(delay)
    return False
