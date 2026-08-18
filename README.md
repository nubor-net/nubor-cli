# nubor

A command-line client for OpenStack clouds. Named configurations you switch
between, backed by `clouds.yaml` — the same file `openstack` and
`openstacksdk` already read, nothing proprietary. Table output by default,
`--format json` or `--format yaml` for scripting. Commands that change state
show exactly what they resolved and ask before acting; `--quiet` skips the
prompt for scripts.

## Commands

| Command | Backs onto |
|---|---|
| `nubor compute instances list / describe / create / delete` | Nova |
| `nubor compute images list` | Glance |
| `nubor compute disks list / create / delete` | Cinder |
| `nubor container clusters list / describe / create / delete` | Magnum |
| `nubor config configurations list / activate` | clouds.yaml |
| `nubor auth login / list` | Keystone |

## Install

Requires Python 3.11 or newer if installing from source. The prebuilt binaries
have no Python requirement.

### Installer

Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/nubor-net/nubor-cli/master/scripts/install.sh | bash
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/nubor-net/nubor-cli/master/scripts/install.ps1 | iex
```

The installer downloads the archive for your platform, verifies it against the
release's `SHA256SUMS`, installs it under `~/.nubor/versions/<version>` with a
stable entry point in `~/.nubor/bin`, and adds that to PATH. Re-running upgrades
in place. Set `NUBOR_VERSION` to install a specific release rather than the
latest.

### From source

```bash
pip install .
```

### Manually

Download the archive for your platform from the releases page along with
`SHA256SUMS`, verify it, and put the binary somewhere on your PATH:

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

Releases also carry build provenance, so a download can be checked against the
workflow and commit that produced it:

```bash
gh attestation verify nubor-0.3.0-linux-x86_64.tar.gz --repo nubor-net/nubor-cli
```

## Auth

nubor never collects or stores a password itself. It connects the way
`openstack` does, resolving the cloud in order:

1. `--cloud <name>` on any command,
2. the active configuration (`nubor config configurations activate <name>`),
3. whatever `openstacksdk` finds on its own — a `clouds.yaml` default cloud,
   or `OS_*` environment variables from a sourced openrc file.

Put your credentials in `~/.config/openstack/clouds.yaml` with whatever auth
method you already use for the `openstack` CLI (an application credential is
a good choice), then:

```bash
nubor config configurations list
nubor config configurations activate <name>
nubor auth login
```

## Examples

```bash
nubor compute instances list
nubor compute instances create web1 --flavor m1.small --image ubuntu-24.04 --network lan --wait
nubor compute instances describe web1 --format json
nubor compute disks create scratch --size 10
nubor compute disks delete scratch          # prompts; add -q to skip
nubor container clusters list
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e . -r requirements-dev.txt
pytest
ruff check . && ruff format --check .
```

Tests never touch a network; the connection is mocked at the `openstack.connect`
boundary.
