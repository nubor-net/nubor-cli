"""API project selection and private break-glass connection handling.

The active configuration is the API project by default and a clouds.yaml entry
only with --direct. Nubor never writes clouds.yaml.
"""

from __future__ import annotations

import ipaddress
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import click
import openstack

from nubor.core.api import ApiConnection

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


def direct_mode() -> bool:
    ctx = click.get_current_context(silent=True)
    option = bool(ctx and ctx.find_root().obj and ctx.find_root().obj.get("direct"))
    return option or os.getenv("NUBOR_DIRECT", "").lower() in {"1", "true", "yes"}


def _api_url() -> str | None:
    ctx = click.get_current_context(silent=True)
    return ctx.find_root().obj.get("api_url") if ctx and ctx.find_root().obj else None


def _private_auth_url(value: str) -> bool:
    host = urlparse(value).hostname
    if not host:
        return False
    if host in {"localhost", "::1"}:
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return host.endswith((".internal", ".lan", ".local"))


def _validate_private_connection(conn):
    auth_url = conn.config.get_auth_args().get("auth_url", "")
    if not _private_auth_url(auth_url):
        raise click.ClickException(
            "--direct accepts only private OpenStack authentication endpoints"
        )
    return conn


def connect(cloud_override: str | None = None):
    """Open the API transport, or an explicitly private direct connection."""
    cloud = cloud_override or active_configuration()
    if not direct_mode():
        return ApiConnection(cloud or os.getenv("NUBOR_PROJECT") or "roger", _api_url())
    try:
        conn = openstack.connect(cloud=cloud) if cloud else openstack.connect()
        return _validate_private_connection(conn)
    except click.ClickException:
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced directly to the user
        click.echo(f"error: could not connect ({exc})", err=True)
        click.echo(
            "hint: check clouds.yaml / OS_* env vars for the private break-glass cloud",
            err=True,
        )
        sys.exit(1)
