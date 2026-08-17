"""The compute group: Nova instances, Glance images, Cinder disks."""

from __future__ import annotations

import click

from nubor.core.config import connect
from nubor.core.confirm import QUIET_OPTION, confirm
from nubor.core.errors import find_or_exit
from nubor.core.output import CLOUD_OPTION, FORMAT_OPTION, emit


@click.group()
def compute() -> None:
    """Nova instances, Glance images, Cinder disks."""


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
        server = conn.compute.wait_for_server(server)
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


# --------------------------------------------------------------------------
# images (Glance)
# --------------------------------------------------------------------------
@compute.group()
def images() -> None:
    """Glance images."""


@images.command("list")
@CLOUD_OPTION
@FORMAT_OPTION
def images_list(cloud_override: str | None, fmt: str) -> None:
    conn = connect(cloud_override)
    rows = [
        {"name": i.name, "status": i.status, "size_bytes": i.size, "visibility": i.visibility}
        for i in conn.image.images()
    ]
    emit(rows, ["name", "status", "size_bytes", "visibility"], fmt)


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
