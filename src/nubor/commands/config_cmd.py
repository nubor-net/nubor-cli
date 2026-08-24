"""Default API project and private break-glass configuration selection."""

from __future__ import annotations

import click

from nubor.core.config import active_configuration, set_active_configuration
from nubor.core.output import FORMAT_OPTION, emit


@click.group()
def config() -> None:
    """Manage the API project and private break-glass configurations."""


@config.group("configurations")
def configurations() -> None:
    """List and activate configurations."""


@configurations.command("list")
@FORMAT_OPTION
def configurations_list(fmt: str) -> None:
    """List the selected API project and locally defined break-glass clouds."""
    from openstack.config import loader

    config_loader = loader.OpenStackConfig()
    active = active_configuration() or "roger"
    names = set(config_loader.cloud_config.get("clouds", {}) or {})
    names.add(active)
    rows = [{"name": name, "is_active": name == active} for name in sorted(names)]
    emit(rows, ["name", "is_active"], fmt)


@configurations.command("activate")
@click.argument("name")
def configurations_activate(name: str) -> None:
    """Set NAME as the active configuration for future commands."""
    set_active_configuration(name)
    click.echo(f"Activated configuration '{name}'.")
