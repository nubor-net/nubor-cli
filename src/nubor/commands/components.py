"""Install and update nubor itself."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import click

from nubor import __version__
from nubor.core.confirm import confirm
from nubor.core.output import FORMAT_OPTION, emit

REPOSITORY = "nubor-net/nubor-cli"
GITHUB_API = f"https://api.github.com/repos/{REPOSITORY}"
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?")


@click.group()
def components() -> None:
    """Inspect and update installed nubor components."""


@components.command("list")
@FORMAT_OPTION
def components_list(fmt: str) -> None:
    """List installed components."""
    emit(
        [{"component": "nubor", "version": __version__, "status": "installed"}],
        ["component", "version", "status"],
        fmt,
    )


def _validated_version(value: str) -> str:
    version = value.removeprefix("v")
    if not VERSION_PATTERN.fullmatch(version):
        raise click.ClickException(f"invalid version '{value}'")
    return version


def _latest_version() -> str:
    request = Request(
        f"{GITHUB_API}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "nubor"},
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed HTTPS host
            release = json.load(response)
    except (OSError, URLError, ValueError) as exc:
        raise click.ClickException("could not determine the latest nubor release") from exc
    tag = release.get("tag_name")
    if not isinstance(tag, str):
        raise click.ClickException("latest nubor release has no version tag")
    return _validated_version(tag)


def _run_installer(version: str) -> None:
    suffix = "ps1" if os.name == "nt" else "sh"
    url = f"https://raw.githubusercontent.com/{REPOSITORY}/v{version}/scripts/install.{suffix}"
    request = Request(url, headers={"User-Agent": "nubor"})
    try:
        with tempfile.TemporaryDirectory(prefix="nubor-update-") as directory:
            script = Path(directory) / f"install.{suffix}"
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS host
                script.write_bytes(response.read())

            env = os.environ.copy()
            env["NUBOR_VERSION"] = version
            if os.name == "nt":
                shell = shutil.which("pwsh") or shutil.which("powershell")
                if not shell:
                    raise click.ClickException("PowerShell is required to update nubor")
                command = [
                    shell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Version",
                    version,
                ]
            else:
                shell = shutil.which("bash")
                if not shell:
                    raise click.ClickException("bash is required to update nubor")
                command = [shell, str(script)]
            subprocess.run(command, env=env, check=True)
    except click.ClickException:
        raise
    except (OSError, URLError, subprocess.CalledProcessError) as exc:
        raise click.ClickException(f"nubor {version} could not be installed") from exc


@components.command("update")
@click.option("--version", "target", help="Install this version instead of the latest release.")
@click.option("--quiet", "quiet", "-q", is_flag=True, help="Skip the confirmation prompt.")
def components_update(target: str | None, quiet: bool) -> None:
    """Update nubor using the checksum-verifying release installer."""
    version = _validated_version(target) if target else _latest_version()
    if version == __version__:
        click.echo(f"nubor {__version__} is already up to date.")
        return
    confirm([f"This will update nubor from {__version__} to {version}."], quiet)
    _run_installer(version)
    click.echo(f"Updated nubor to {version}.")
