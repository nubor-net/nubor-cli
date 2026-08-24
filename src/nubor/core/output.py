"""Output formatting shared by every command."""

from __future__ import annotations

import json
import sys
from typing import Any

import click
from tabulate import tabulate

FORMAT_OPTION = click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format (default: table).",
)
CLOUD_OPTION = click.option(
    "--cloud",
    "cloud_override",
    default=None,
    help=(
        "API project to use for this call; with --direct, a clouds.yaml entry "
        "(overrides the active configuration)."
    ),
)


def emit(rows: list[dict[str, Any]], columns: list[str], fmt: str) -> None:
    """Print rows as a table, or as JSON/YAML for scripting.

    Rows are round-tripped through JSON first: openstacksdk resource dicts
    contain its own Munch/Resource wrapper types, which json.dumps(default=str)
    flattens to plain strings, but a raw yaml.dump() on the original dict would
    serialize those internal types verbatim ("!!python/object/new:..." tags in
    the output). Normalizing through JSON once guarantees every downstream
    format sees plain primitives.
    """
    rows = json.loads(json.dumps(rows, default=str))

    if fmt == "json":
        click.echo(json.dumps(rows, indent=2))
        return
    if fmt == "yaml":
        try:
            import yaml
        except ImportError:
            click.echo("error: pyyaml not installed (pip install pyyaml)", err=True)
            sys.exit(1)
        click.echo(yaml.dump(rows, sort_keys=False))
        return
    table = [[r.get(c, "") for c in columns] for r in rows]
    click.echo(tabulate(table, headers=[c.upper() for c in columns]))
