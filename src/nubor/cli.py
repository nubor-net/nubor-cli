"""Root command group."""

from __future__ import annotations

import click

from nubor import __version__
from nubor.commands.auth import auth
from nubor.commands.compute import compute
from nubor.commands.config_cmd import config
from nubor.commands.container import container


@click.group()
@click.version_option(__version__, prog_name="nubor")
def main() -> None:
    """nubor: a command-line client for OpenStack clouds."""


main.add_command(auth)
main.add_command(compute)
main.add_command(config)
main.add_command(container)
