"""The config group: named configurations, backed 1:1 by clouds.yaml entries."""

from __future__ import annotations

import click

from nubor.core.config import active_configuration, set_active_configuration
from nubor.core.output import FORMAT_OPTION, emit


@click.group()
def config() -> None:
    """Manage named configurations (clouds.yaml entries)."""


@config.group("configurations")
def configurations() -> None:
    """List and activate configurations."""


@configurations.command("list")
@FORMAT_OPTION
def configurations_list(fmt: str) -> None:
    """List every cloud defined in clouds.yaml, marking the active one."""
    from openstack.config import loader

    config_loader = loader.OpenStackConfig()
    active = active_configuration()
    rows = [
        {"name": name, "is_active": name == active}
        for name in config_loader.cloud_config.get("clouds", {}) or {}
    ]
    if not rows:
        click.echo("No clouds found in clouds.yaml.", err=True)
        return
    emit(rows, ["name", "is_active"], fmt)


@configurations.command("activate")
@click.argument("name")
def configurations_activate(name: str) -> None:
    """Set NAME as the active configuration for future commands."""
    set_active_configuration(name)
    click.echo(f"Activated configuration '{name}'.")
