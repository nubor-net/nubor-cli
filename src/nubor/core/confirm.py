"""Confirmation prompts for commands that change state."""

from __future__ import annotations

import sys
from collections.abc import Sequence

import click

QUIET_OPTION = click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Skip confirmation prompts (for scripting).",
)


def confirm(lines: Sequence[str], quiet: bool) -> None:
    """Show what is about to happen and ask before doing it.

    Callers must not have made any state-changing API call before this point:
    declining exits 1 and the guarantee is that nothing happened.
    """
    for line in lines:
        click.echo(line)
    if quiet:
        return
    if not click.confirm("Do you want to continue?", default=True):
        click.echo("Aborted.", err=True)
        sys.exit(1)
