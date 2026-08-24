"""OIDC device login and private break-glass authentication."""

from __future__ import annotations

import click

from nubor.core.api import ApiConnection
from nubor.core.config import active_configuration, connect, direct_mode
from nubor.core.output import CLOUD_OPTION


@click.group()
def auth() -> None:
    """Log in through OIDC, or inspect private break-glass credentials."""


@auth.command("login")
@CLOUD_OPTION
def auth_login(cloud_override: str | None) -> None:
    """Log in with OIDC Device Flow and MFA, or verify --direct credentials."""
    conn = connect(cloud_override)
    if isinstance(conn, ApiConnection):
        identity = conn.client.device_login()
        click.echo(
            f"Connected as project '{identity['project']['name']}' "
            f"(id: {identity['project']['id']})"
        )
        click.echo(f"User: {identity['user']['name']}")
        click.echo(f"API URL: {conn.client.api_url}")
        return
    token = conn.session.auth.get_access(conn.session)
    click.echo(f"Connected as project '{token.project_name}' (id: {token.project_id})")
    click.echo(f"User: {token.username if hasattr(token, 'username') else '(token-based)'}")
    click.echo(f"Auth URL: {conn.config.get_auth_args().get('auth_url', '(from env)')}")


@auth.command("list")
def auth_list() -> None:
    """Show which configuration future commands will use."""
    active = active_configuration()
    if direct_mode():
        click.echo(f"Private break-glass cloud: {active or '(clouds.yaml default / OS_* env)'}")
    else:
        click.echo(f"Nubor API project: {active or 'roger'}")


@auth.command("logout")
@CLOUD_OPTION
def auth_logout(cloud_override: str | None) -> None:
    """Revoke the API token and remove the local credential-store entry."""
    conn = connect(cloud_override)
    if not isinstance(conn, ApiConnection):
        raise click.ClickException("logout is available for API sessions, not --direct")
    conn.client.logout()
    click.echo("Logged out.")
