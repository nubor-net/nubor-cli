"""OpenStack compute resources: instances, flavors, networks, images, and disks."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

import click
import openstack

from nubor.core import ssh as ssh_helpers
from nubor.core.config import connect
from nubor.core.confirm import QUIET_OPTION, confirm
from nubor.core.errors import find_or_exit
from nubor.core.output import CLOUD_OPTION, FORMAT_OPTION, emit


@click.group()
def compute() -> None:
    """Nova, Neutron, Glance, and Cinder resources."""


# --------------------------------------------------------------------------
# instances (Nova)
# --------------------------------------------------------------------------
@compute.group()
def instances() -> None:
    """Nova server instances."""


@instances.command("list")
@CLOUD_OPTION
@FORMAT_OPTION
def instances_list(cloud_override: str | None, fmt: str) -> None:
    conn = connect(cloud_override)
    rows = [
        {
            "name": s.name,
            "status": s.status,
            "flavor": (s.flavor or {}).get("original_name") or (s.flavor or {}).get("id", ""),
            "image": (s.image or {}).get("id", "") if isinstance(s.image, dict) else "",
            "addresses": ",".join(a["addr"] for net in (s.addresses or {}).values() for a in net),
        }
        for s in conn.compute.servers()
    ]
    emit(rows, ["name", "status", "flavor", "addresses"], fmt)


@instances.command("describe")
@click.argument("name_or_id")
@CLOUD_OPTION
@FORMAT_OPTION
def instances_describe(name_or_id: str, cloud_override: str | None, fmt: str) -> None:
    conn = connect(cloud_override)
    server = find_or_exit(conn.compute.find_server, name_or_id, "instance")
    emit([server.to_dict()], list(server.to_dict().keys()), fmt if fmt != "table" else "yaml")


@instances.command("create")
@click.argument("name")
@click.option("--flavor", required=True, help="Flavor name or ID.")
@click.option("--image", required=True, help="Image name or ID.")
@click.option("--network", required=True, help="Network name or ID.")
@click.option("--key-name", default=None, help="Keypair to inject.")
@click.option("--wait", is_flag=True, help="Wait until the instance is ACTIVE.")
@QUIET_OPTION
@CLOUD_OPTION
def instances_create(
    name: str,
    flavor: str,
    image: str,
    network: str,
    key_name: str | None,
    wait: bool,
    quiet: bool,
    cloud_override: str | None,
) -> None:
    """Boot a new instance."""
    conn = connect(cloud_override)
    flavor_obj = find_or_exit(conn.compute.find_flavor, flavor, "flavor")
    image_obj = find_or_exit(conn.image.find_image, image, "image")
    network_obj = find_or_exit(conn.network.find_network, network, "network")
    confirm(
        [
            f"This will create instance '{name}':",
            f"  flavor:  {flavor_obj.name} ({flavor_obj.id})",
            f"  image:   {image_obj.name} ({image_obj.id})",
            f"  network: {network_obj.name} ({network_obj.id})",
        ]
        + ([f"  keypair: {key_name}"] if key_name else []),
        quiet,
    )
    args: dict = {
        "name": name,
        "flavor_id": flavor_obj.id,
        "image_id": image_obj.id,
        "networks": [{"uuid": network_obj.id}],
    }
    if key_name:
        args["key_name"] = key_name
    server = conn.compute.create_server(**args)
    if wait:
        try:
            server = conn.compute.wait_for_server(server)
        except openstack.exceptions.ResourceFailure as exc:
            server = conn.compute.get_server(server.id)
            fault = getattr(server, "fault", None) or {}
            reason = fault.get("message") or str(exc)
            raise click.ClickException(
                f"instance '{server.name}' (id: {server.id}) entered ERROR: {reason}"
            ) from None
    click.echo(f"Created instance '{server.name}' (id: {server.id}, status: {server.status}).")


@instances.command("delete")
@click.argument("name_or_id")
@click.option("--wait", is_flag=True, help="Wait until the instance is gone.")
@QUIET_OPTION
@CLOUD_OPTION
def instances_delete(name_or_id: str, wait: bool, quiet: bool, cloud_override: str | None) -> None:
    """Delete an instance."""
    conn = connect(cloud_override)
    server = find_or_exit(conn.compute.find_server, name_or_id, "instance")
    confirm(
        [f"This will delete instance '{server.name}' (id: {server.id}, status: {server.status})."],
        quiet,
    )
    conn.compute.delete_server(server)
    if wait:
        conn.compute.wait_for_delete(server)
    click.echo(f"Deleted instance '{server.name}'.")


@instances.command("start")
@click.argument("name_or_id")
@QUIET_OPTION
@CLOUD_OPTION
def instances_start(name_or_id: str, quiet: bool, cloud_override: str | None) -> None:
    """Start a stopped instance."""
    conn = connect(cloud_override)
    server = find_or_exit(conn.compute.find_server, name_or_id, "instance")
    confirm([f"This will start instance '{server.name}' (status: {server.status})."], quiet)
    conn.compute.start_server(server)
    click.echo(f"Started instance '{server.name}'.")


@instances.command("stop")
@click.argument("name_or_id")
@QUIET_OPTION
@CLOUD_OPTION
def instances_stop(name_or_id: str, quiet: bool, cloud_override: str | None) -> None:
    """Stop a running instance."""
    conn = connect(cloud_override)
    server = find_or_exit(conn.compute.find_server, name_or_id, "instance")
    confirm([f"This will stop instance '{server.name}' (status: {server.status})."], quiet)
    conn.compute.stop_server(server)
    click.echo(f"Stopped instance '{server.name}'.")


@instances.command("reboot")
@click.argument("name_or_id")
@click.option("--hard", is_flag=True, help="Power-cycle instead of requesting a soft reboot.")
@QUIET_OPTION
@CLOUD_OPTION
def instances_reboot(name_or_id: str, hard: bool, quiet: bool, cloud_override: str | None) -> None:
    """Reboot an instance (soft by default)."""
    conn = connect(cloud_override)
    server = find_or_exit(conn.compute.find_server, name_or_id, "instance")
    reboot_type = "HARD" if hard else "SOFT"
    confirm(
        [
            f"This will {reboot_type.lower()} reboot instance '{server.name}' "
            f"(status: {server.status})."
        ],
        quiet,
    )
    conn.compute.reboot_server(server, reboot_type)
    click.echo(f"Rebooted instance '{server.name}' ({reboot_type.lower()}).")


@instances.command("ssh-proxy")
@click.argument("command", required=False)
@click.option("--clear", is_flag=True, help="Forget the saved proxy command.")
def instances_ssh_proxy(command: str | None, clear: bool) -> None:
    """Show, set, or clear the proxy `instances ssh` falls back to.

    Once set, a plain `nubor compute instances ssh NAME` tries the direct route
    and goes through the proxy when there is none - no flag to remember:

        nubor compute instances ssh-proxy "cloudflared access ssh --hostname {instance}.ssh.example.net"

    {instance} and {address} are filled in per connection.
    """  # noqa: E501 - the example is a single command, wrapping it would break copy-paste
    if clear:
        ssh_helpers.clear_proxy_command()
        click.echo("Cleared the saved ssh proxy command.")
        return
    if not command:
        click.echo(ssh_helpers.saved_proxy_command() or "(none saved)")
        return
    ssh_helpers.save_proxy_command(command)
    click.echo(f"Saved: {command}")


@instances.command("ssh", context_settings={"ignore_unknown_options": True})
@click.argument("name_or_id")
@click.argument("ssh_args", nargs=-1, type=click.UNPROCESSED)
@click.option("--user", default=None, help="SSH login user (default: resolved from metadata).")
@click.option("--key-file", default=None, help="Private key to use (passed to ssh -i).")
@click.option("--internal-ip", is_flag=True, help="Use the fixed IP, not the floating IP.")
@click.option("--dry-run", is_flag=True, help="Print the ssh command instead of running it.")
@click.option(
    "--ephemeral-key/--no-ephemeral-key",
    default=None,
    help="Mint a short-lived key and inject it via instance metadata "
    "(default: on when the instance or image is marked nubor_agent=true).",
)
@click.option(
    "--tunnel-through",
    metavar="HOST",
    default=None,
    help="Reach the instance via ssh -J HOST when there is no route from here. "
    "Defaults to $NUBOR_SSH_TUNNEL.",
)
@click.option(
    "--proxy-command",
    metavar="CMD",
    default=None,
    help="Reach the instance through an identity-aware proxy (Cloudflare Access, Teleport, "
    "Boundary): passed to ssh as ProxyCommand. ssh expands %h/%p; nubor expands "
    "{instance} and {address}. Defaults to $NUBOR_SSH_PROXY_COMMAND, then the saved one.",
)
@click.option(
    "--key-ttl",
    type=click.IntRange(30, 3600),
    default=300,
    show_default=True,
    help="Seconds an injected ephemeral key stays valid.",
)
@CLOUD_OPTION
def instances_ssh(
    name_or_id: str,
    ssh_args: tuple[str, ...],
    user: str | None,
    key_file: str | None,
    internal_ip: bool,
    dry_run: bool,
    ephemeral_key: bool | None,
    tunnel_through: str | None,
    proxy_command: str | None,
    key_ttl: int,
    cloud_override: str | None,
) -> None:
    """SSH into an instance, resolving its address and login user from Nova.

    Everything after the instance name is handed to ssh untouched, so the usual
    flags and remote commands work:

        nubor compute instances ssh web-1 -- -L 8080:localhost:80
        nubor compute instances ssh web-1 -- uptime

    Your own keys are never touched: ssh picks them up from ~/.ssh/config and
    the agent exactly as if you had typed the address yourself.
    """
    conn = connect(cloud_override)
    server = find_or_exit(conn.compute.find_server, name_or_id, "instance")
    # find_server returns a summary record; addresses only come back in full.
    server = conn.compute.get_server(server.id)

    address = ssh_helpers.pick_address(server, internal_ip)
    if not address:
        which = "fixed" if internal_ip else "any"
        click.echo(f"error: instance '{server.name}' has no {which} IP address", err=True)
        if not internal_ip:
            click.echo("hint: it may still be building, or need a floating IP", err=True)
        sys.exit(1)

    if not user:
        user, source = ssh_helpers.resolve_user(conn, server)
        if not user:
            click.echo(f"error: nothing declares a login user for '{server.name}'", err=True)
            click.echo("hint: pass --user, or declare it once so every tool knows:", err=True)
            click.echo(
                "        openstack image set --property os_admin_user=ubuntu <image>", err=True
            )
            sys.exit(1)
        click.echo(f"# login user '{user}' from {source}", err=True)

    if ephemeral_key is None:  # not forced either way - use it when it will work
        ephemeral_key = ssh_helpers.agent_present(conn, server)

    tunnel = tunnel_through or os.environ.get("NUBOR_SSH_TUNNEL")
    proxy = (
        proxy_command
        or os.environ.get("NUBOR_SSH_PROXY_COMMAND")
        or ssh_helpers.saved_proxy_command()
    )
    if tunnel and proxy:
        # -J is implemented as a ProxyCommand, so setting both means one
        # silently wins. Refuse rather than pick.
        click.echo("error: --tunnel-through and --proxy-command are alternatives", err=True)
        sys.exit(1)

    if not dry_run and not tunnel:
        # Try the direct path first and fall back to the proxy on its own, so
        # the common case stays a bare `instances ssh NAME`. The probe is short
        # when there is somewhere to fall back to and patient when there is
        # not, because then the only thing worth waiting for is a booting
        # instance.
        attempts, delay = (2, 3) if proxy else (12, 5)
        if ssh_helpers.wait_for_port(address, attempts=attempts, delay=delay):
            proxy = None  # reachable directly; no need to involve anything else
        elif proxy:
            click.echo(f"# no direct route to {address}, going through the proxy", err=True)
        else:
            # Reported before minting anything: an unreachable address is not
            # the guest's fault, and writing a key we cannot use would only
            # leave litter in the instance's metadata.
            click.echo(f"error: nothing is answering on {address}:22", err=True)
            click.echo("hint: the usual causes, in the order worth checking -", err=True)
            click.echo("        - no floating IP on the instance (or it is not routed)", err=True)
            click.echo("        - a security group that does not allow 22 from here", err=True)
            click.echo("        - the instance is still booting", err=True)
            click.echo("      to go through a proxy or bastion instead, either pass", err=True)
            click.echo("        --proxy-command / --tunnel-through, or save a default:", err=True)
            click.echo(
                f'        nubor compute instances ssh-proxy "{ssh_helpers.EXAMPLE_PROXY_COMMAND}"',
                err=True,
            )
            sys.exit(1)

    if proxy:
        proxy = proxy.format(instance=server.name, address=address)

    workdir = tempfile.mkdtemp(prefix="nubor-ssh-") if ephemeral_key and not dry_run else None
    metadata_key = None
    try:
        if workdir:
            key_file, public_key = ssh_helpers.mint_ephemeral_key(workdir)
            metadata_key = ssh_helpers.inject_key(conn, server, user, public_key, key_ttl)
            click.echo(f"# injected an ephemeral key, valid {key_ttl}s", err=True)

        cmd = ["ssh"]
        if key_file:
            # IdentitiesOnly stops ssh offering every key in the agent first and
            # tripping MaxAuthTries before it reaches this one.
            cmd += ["-i", key_file, "-o", "IdentitiesOnly=yes"]
        if proxy:
            cmd += ["-o", f"ProxyCommand={proxy}"]
        if tunnel:
            # ProxyJump reaches an instance with no route from here by way of
            # one that has. ssh carries the ephemeral key through unchanged.
            cmd += ["-J", tunnel]
        cmd += [f"{user}@{address}", *ssh_args]

        click.echo(f"# {' '.join(cmd)}", err=True)
        if dry_run:
            if ephemeral_key:
                click.echo("# (would inject an ephemeral key first)", err=True)
            return
        if not workdir and server.key_name:
            # We cannot supply the key, only name the one the instance booted
            # with, so a "Permission denied" has an obvious lead to follow.
            click.echo(f"# instance keypair: {server.key_name}", err=True)

        base = cmd[: -len(ssh_args)] if ssh_args else cmd
        if workdir and not ssh_helpers.wait_for_key(base):
            # We already know the port answers, so this really is the key.
            click.echo(f"error: {server.name} reachable, but it never accepted the key", err=True)
            click.echo(
                "hint: check 'systemctl status nubor-ssh-agent' in the guest "
                f"(user '{user}' must exist there)",
                err=True,
            )
            sys.exit(1)
        try:
            sys.exit(subprocess.call(cmd))
        except FileNotFoundError:
            click.echo("error: no 'ssh' client found on PATH", err=True)
            sys.exit(1)
    finally:
        # Revoke on the way out, however we leave. The expiry is the backstop
        # for what this cannot cover (SIGKILL, lost network).
        if metadata_key:
            try:
                conn.compute.delete_server_metadata(server, [metadata_key])
            except openstack.exceptions.SDKException as exc:
                click.echo(f"warning: could not revoke ephemeral key ({exc})", err=True)
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)


# --------------------------------------------------------------------------
# images (Glance)
# --------------------------------------------------------------------------
@compute.group()
def images() -> None:
    """Glance images."""


@images.command("list")
@click.option("--all", "show_all", is_flag=True, help="Include images without nubor_agent=true.")
@CLOUD_OPTION
@FORMAT_OPTION
def images_list(show_all: bool, cloud_override: str | None, fmt: str) -> None:
    """List images carrying the nubor agent (--all for every image).

    An image without nubor_agent=true still boots fine; it just cannot take an
    ephemeral key, so it is hidden here to keep the supported set obvious.
    """
    conn = connect(cloud_override)
    listed = [i for i in conn.image.images() if show_all or ssh_helpers.has_agent_property(i)]
    rows = [
        {
            "name": i.name,
            "status": i.status,
            "size_bytes": i.size,
            "visibility": i.visibility,
            "nubor_agent": ssh_helpers.has_agent_property(i),
        }
        for i in listed
    ]
    columns = ["name", "status", "size_bytes", "visibility"]
    if show_all:
        columns.append("nubor_agent")
    if not rows and not show_all:
        # Silence here would read as "no images", which is a different problem.
        click.echo("No images carry nubor_agent=true. Use --all to see them.", err=True)
        click.echo("hint: openstack image set --property nubor_agent=true <image>", err=True)
        return
    emit(rows, columns, fmt)


@images.command("prune")
@click.option("--dry-run", is_flag=True, help="List what would go, then stop.")
@QUIET_OPTION
@CLOUD_OPTION
def images_prune(dry_run: bool, quiet: bool, cloud_override: str | None) -> None:
    """Delete images carrying neither nubor_agent=true nor nubor_keep=true.

    Mark service images - Octavia amphora, Trove guest, Manila, Magnum node
    images - with nubor_keep=true first. They will never carry the agent, and
    the cloud loses those services without them:

        openstack image set --property nubor_keep=true amphora-x64-haproxy

    Images an instance is booted from are skipped: Glance refuses those anyway,
    and naming them is more useful than a mid-loop error.
    """
    conn = connect(cloud_override)
    doomed = [
        i
        for i in conn.image.images()
        if not ssh_helpers.has_agent_property(i) and not ssh_helpers.is_protected(i)
    ]
    if not doomed:
        click.echo("Nothing to prune: every image carries nubor_agent=true or nubor_keep=true.")
        return

    try:
        in_use = {
            (s.image or {}).get("id")
            for s in conn.compute.servers(all_projects=True)
            if isinstance(s.image, dict)
        }
    except openstack.exceptions.HttpException:
        # Without admin we only see our own project's servers, so "unused" here
        # would mean "unused BY ME" - not a safe basis for deleting a shared or
        # public image. Say so instead of quietly pruning someone else's boot
        # image.
        click.echo(
            "error: cannot list instances across projects, so 'in use' is unknowable", err=True
        )
        click.echo("hint: run as an admin, or protect images with nubor_keep=true", err=True)
        sys.exit(1)

    keep = [i for i in doomed if i.id in in_use]
    doomed = [i for i in doomed if i.id not in in_use]

    lines = [f"skip   {i.name} (an instance is booted from it)" for i in keep]
    lines += [f"delete {i.name} ({i.id})" for i in doomed]
    if not doomed:
        for line in lines:
            click.echo(line)
        click.echo("\nNothing left to delete.")
        return
    if dry_run:
        for line in lines:
            click.echo(line)
        click.echo(f"\nDry run. {len(doomed)} image(s) would be deleted.")
        return

    confirm([*lines, f"\nThis will permanently delete {len(doomed)} image(s)."], quiet)
    for image in doomed:
        try:
            conn.image.delete_image(image)
            click.echo(f"deleted {image.name}")
        except openstack.exceptions.SDKException as exc:
            click.echo(f"error: could not delete {image.name}: {exc}", err=True)


# --------------------------------------------------------------------------
# flavors (Nova)
# --------------------------------------------------------------------------
@compute.group()
def flavors() -> None:
    """Nova instance flavors."""


@flavors.command("list")
@CLOUD_OPTION
@FORMAT_OPTION
def flavors_list(cloud_override: str | None, fmt: str) -> None:
    conn = connect(cloud_override)
    rows = [
        {
            "name": flavor.name,
            "vcpus": flavor.vcpus,
            "ram_mb": flavor.ram,
            "disk_gb": flavor.disk,
            "public": flavor.is_public,
        }
        for flavor in conn.compute.flavors()
    ]
    emit(rows, ["name", "vcpus", "ram_mb", "disk_gb", "public"], fmt)


# --------------------------------------------------------------------------
# networks (Neutron)
# --------------------------------------------------------------------------
@compute.group()
def networks() -> None:
    """Neutron networks."""


@networks.command("list")
@CLOUD_OPTION
@FORMAT_OPTION
def networks_list(cloud_override: str | None, fmt: str) -> None:
    conn = connect(cloud_override)
    rows = [
        {
            "name": network.name,
            "status": network.status,
            "shared": network.is_shared,
            "external": network.is_router_external,
            "subnets": ",".join(network.subnet_ids or []),
        }
        for network in conn.network.networks()
    ]
    emit(rows, ["name", "status", "shared", "external", "subnets"], fmt)


# --------------------------------------------------------------------------
# disks (Cinder)
# --------------------------------------------------------------------------
@compute.group()
def disks() -> None:
    """Cinder block-storage volumes."""


@disks.command("list")
@CLOUD_OPTION
@FORMAT_OPTION
def disks_list(cloud_override: str | None, fmt: str) -> None:
    conn = connect(cloud_override)
    rows = [
        {
            "name": v.name,
            "status": v.status,
            "size_gb": v.size,
            "attached_to": ",".join(a.get("server_id", "") for a in (v.attachments or [])),
        }
        for v in conn.block_storage.volumes()
    ]
    emit(rows, ["name", "status", "size_gb", "attached_to"], fmt)


@disks.command("create")
@click.argument("name")
@click.option("--size", required=True, type=int, help="Size in GB.")
@QUIET_OPTION
@CLOUD_OPTION
def disks_create(name: str, size: int, quiet: bool, cloud_override: str | None) -> None:
    """Create a new volume."""
    conn = connect(cloud_override)
    confirm([f"This will create disk '{name}' ({size} GB)."], quiet)
    volume = conn.block_storage.create_volume(name=name, size=size)
    click.echo(f"Created disk '{volume.name}' (id: {volume.id}, status: {volume.status}).")


@disks.command("delete")
@click.argument("name_or_id")
@QUIET_OPTION
@CLOUD_OPTION
def disks_delete(name_or_id: str, quiet: bool, cloud_override: str | None) -> None:
    """Delete a volume."""
    conn = connect(cloud_override)
    volume = find_or_exit(conn.block_storage.find_volume, name_or_id, "disk")
    confirm(
        [
            f"This will delete disk '{volume.name}' "
            f"(id: {volume.id}, size: {volume.size} GB, status: {volume.status})."
        ],
        quiet,
    )
    conn.block_storage.delete_volume(volume)
    click.echo(f"Deleted disk '{volume.name}'.")
