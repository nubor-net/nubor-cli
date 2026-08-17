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

```bash
pip install .
```

Or build a standalone binary (no Python required to run it):

```bash
pip install -r requirements-dev.txt
./scripts/build-binary.sh
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
