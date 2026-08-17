"""Error handling shared by every command."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

import click
import openstack


def find_or_exit(finder: Callable[..., Any], name_or_id: str, resource_label: str) -> Any:
    """Run a `conn.*.find_*(name_or_id, ignore_missing=False)` call and turn
    its NotFoundException into a one-line error instead of a traceback -
    the same failure-handling shape as core.config.connect().
    """
    try:
        return finder(name_or_id, ignore_missing=False)
    except openstack.exceptions.NotFoundException:
        click.echo(f"error: no {resource_label} found matching '{name_or_id}'", err=True)
        sys.exit(1)
    except openstack.exceptions.SDKException as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
