"""The auth group.

nubor never collects or stores credentials itself; clouds.yaml holds whatever
auth method the user configured (password, application credential, token).
These commands only verify and report.
"""

from __future__ import annotations

import click

from nubor.core.config import active_configuration, connect
from nubor.core.output import CLOUD_OPTION


@click.group()
def auth() -> None:
    """Verify and inspect credentials (held in clouds.yaml, not by nubor)."""


@auth.command("login")
@CLOUD_OPTION
def auth_login(cloud_override: str | None) -> None:
    """Verify the active (or given) cloud's credentials actually work."""
    conn = connect(cloud_override)
    token = conn.session.auth.get_access(conn.session)
    click.echo(f"Connected as project '{token.project_name}' (id: {token.project_id})")
    click.echo(f"User: {token.username if hasattr(token, 'username') else '(token-based)'}")
    click.echo(f"Auth URL: {conn.config.get_auth_args().get('auth_url', '(from env)')}")


@auth.command("list")
def auth_list() -> None:
    """Show which configuration future commands will use."""
    active = active_configuration()
    click.echo(f"Active configuration: {active or '(none - using clouds.yaml default / OS_* env)'}")
