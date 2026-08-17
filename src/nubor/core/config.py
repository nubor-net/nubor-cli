"""Connection and configuration handling.

Named configurations are clouds.yaml entries; nubor never writes to that file.
The only state nubor keeps is the name of the active configuration, in
~/.config/nubor/active_configuration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import openstack

STATE_DIR = Path.home() / ".config" / "nubor"
ACTIVE_CONFIG_FILE = STATE_DIR / "active_configuration"


def active_configuration() -> str | None:
    if ACTIVE_CONFIG_FILE.exists():
        name = ACTIVE_CONFIG_FILE.read_text().strip()
        return name or None
    return None


def set_active_configuration(name: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_CONFIG_FILE.write_text(name)


def connect(cloud_override: str | None = None) -> openstack.connection.Connection:
    """Open a connection, resolving the cloud in order of precedence:
    an explicit --cloud value, the active configuration, then whatever
    openstacksdk finds on its own (a clouds.yaml default cloud, or OS_*
    environment variables - which is what lets the tool work unmodified
    inside an openrc-sourced shell).
    """
    cloud = cloud_override or active_configuration()
    try:
        return openstack.connect(cloud=cloud) if cloud else openstack.connect()
    except Exception as exc:  # noqa: BLE001 - surfaced directly to the user
        click.echo(f"error: could not connect ({exc})", err=True)
        click.echo(
            "hint: run 'nubor auth login' or check clouds.yaml / OS_* env vars",
            err=True,
        )
        sys.exit(1)
