"""The container group: Magnum Kubernetes clusters."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from nubor.core import kube
from nubor.core.config import connect
from nubor.core.confirm import QUIET_OPTION, confirm
from nubor.core.errors import find_or_exit
from nubor.core.output import CLOUD_OPTION, FORMAT_OPTION, emit


@click.group()
def container() -> None:
    """Magnum Kubernetes clusters."""


@container.group()
def clusters() -> None:
    """Magnum Kubernetes clusters."""


@clusters.command("list")
@CLOUD_OPTION
@FORMAT_OPTION
def clusters_list(cloud_override: str | None, fmt: str) -> None:
    conn = connect(cloud_override)
    rows = [
        {
            "name": c.name,
            "status": c.status,
            "node_count": c.node_count,
            "master_count": c.master_count,
            "keypair": c.keypair,
        }
        for c in conn.container_infrastructure_management.clusters()
    ]
    emit(rows, ["name", "status", "node_count", "master_count", "keypair"], fmt)


@clusters.command("describe")
@click.argument("name_or_id")
@CLOUD_OPTION
@FORMAT_OPTION
def clusters_describe(name_or_id: str, cloud_override: str | None, fmt: str) -> None:
    conn = connect(cloud_override)
    cluster = find_or_exit(
        conn.container_infrastructure_management.find_cluster, name_or_id, "cluster"
    )
    emit([cluster.to_dict()], list(cluster.to_dict().keys()), fmt if fmt != "table" else "yaml")


@clusters.command("create")
@click.argument("name")
@click.option("--cluster-template", required=True, help="Cluster template name or ID.")
@click.option("--node-count", required=True, type=int, help="Number of worker nodes.")
@click.option("--master-count", default=1, type=int, show_default=True)
@click.option("--keypair", default=None, help="Keypair for node access.")
@QUIET_OPTION
@CLOUD_OPTION
def clusters_create(
    name: str,
    cluster_template: str,
    node_count: int,
    master_count: int,
    keypair: str | None,
    quiet: bool,
    cloud_override: str | None,
) -> None:
    """Create a new Kubernetes cluster."""
    conn = connect(cloud_override)
    template = find_or_exit(
        conn.container_infrastructure_management.find_cluster_template,
        cluster_template,
        "cluster template",
    )
    confirm(
        [
            f"This will create cluster '{name}':",
            f"  template: {template.name} ({template.uuid})",
            f"  nodes:    {node_count} worker(s), {master_count} master(s)",
        ]
        + ([f"  keypair:  {keypair}"] if keypair else []),
        quiet,
    )
    args: dict = {
        "name": name,
        "cluster_template_id": template.uuid,
        "node_count": node_count,
        "master_count": master_count,
    }
    if keypair:
        args["keypair"] = keypair
    cluster = conn.container_infrastructure_management.create_cluster(**args)
    click.echo(f"Created cluster '{name}' (id: {cluster.uuid}). Provisioning takes a while.")


@clusters.command("delete")
@click.argument("name_or_id")
@QUIET_OPTION
@CLOUD_OPTION
def clusters_delete(name_or_id: str, quiet: bool, cloud_override: str | None) -> None:
    """Delete a Kubernetes cluster."""
    conn = connect(cloud_override)
    cluster = find_or_exit(
        conn.container_infrastructure_management.find_cluster, name_or_id, "cluster"
    )
    confirm(
        [
            f"This will delete cluster '{cluster.name}' "
            f"(id: {cluster.uuid}, status: {cluster.status}) and all of its nodes."
        ],
        quiet,
    )
    conn.container_infrastructure_management.delete_cluster(cluster)
    click.echo(f"Deleted cluster '{cluster.name}'.")


@clusters.command("get-credentials")
@click.argument("name_or_id")
@click.option(
    "--kubeconfig",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="File to write. Defaults to $KUBECONFIG's first entry, else ~/.kube/config.",
)
@click.option(
    "--context", "context_name", default=None, help="Context name. Defaults to the cluster name."
)
@CLOUD_OPTION
def clusters_get_credentials(
    name_or_id: str,
    kubeconfig: Path | None,
    context_name: str | None,
    cloud_override: str | None,
) -> None:
    """Write kubeconfig credentials for a cluster, so kubectl can reach it.

    Magnum signs a client certificate from a CSR generated here; the private key
    is written into the kubeconfig and never sent to the cloud.
    """
    conn = connect(cloud_override)
    cluster = find_or_exit(
        conn.container_infrastructure_management.find_cluster, name_or_id, "cluster"
    )
    if not cluster.api_address:
        click.echo(
            f"error: cluster '{cluster.name}' has no API address yet (status: {cluster.status})",
            err=True,
        )
        sys.exit(1)

    ca_pem = client_pem = key_pem = None
    if not cluster.tls_disabled:
        magnum = conn.container_infrastructure_management
        ca_pem = magnum.get_cluster_certificate(cluster.uuid).pem
        key_pem, csr_pem = kube.new_csr()
        client_pem = magnum.create_cluster_certificate(
            cluster_uuid=cluster.uuid, csr=csr_pem.decode()
        ).pem

    context = context_name or cluster.name
    path = kubeconfig or kube.default_path()
    kube.merge(path, *kube.entries(context, cluster.api_address, ca_pem, client_pem, key_pem))
    click.echo(f"Wrote credentials for '{cluster.name}' to {path} (context: {context}).")
