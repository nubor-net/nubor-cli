"""Root command group."""

from __future__ import annotations

import click

from nubor import __version__
from nubor.commands.auth import auth
from nubor.commands.components import components
from nubor.commands.compute import compute
from nubor.commands.config_cmd import config
from nubor.commands.container import container


@click.group()
@click.version_option(__version__, prog_name="nubor")
@click.option(
    "--direct",
    is_flag=True,
    help="Use a private OpenStack endpoint directly (break-glass mode).",
)
@click.option("--api-url", default=None, help="Override https://api.nubor.net.")
@click.pass_context
def main(ctx: click.Context, direct: bool, api_url: str | None) -> None:
    """nubor: the command-line client for the Nubor API."""
    ctx.ensure_object(dict)
    ctx.obj.update({"direct": direct, "api_url": api_url})


main.add_command(auth)
main.add_command(compute)
main.add_command(components)
main.add_command(config)
main.add_command(container)
