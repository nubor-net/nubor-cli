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
| `nubor compute instances list / describe / create / delete / start / stop / reboot / ssh` | Nova |
| `nubor compute flavors list` | Nova |
| `nubor compute networks list` | Neutron |
| `nubor compute images list / prune` | Glance |
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
nubor compute instances stop web1
nubor compute instances start web1
nubor compute instances reboot web1       # add --hard to power-cycle
nubor compute flavors list
nubor compute networks list
nubor compute disks create scratch --size 10
nubor compute disks delete scratch          # prompts; add -q to skip
nubor container clusters list
nubor compute instances ssh web1
nubor compute instances ssh web1 -- -L 8080:localhost:80    # after -- goes to ssh
```

## SSH

`nubor compute instances ssh NAME` resolves the address from Nova and hands off
to your system `ssh`, so config, agent, and every flag work as usual.

### The login user

Nova knows the address; it does not know which account your key landed in.
nubor takes the first answer it finds:

1. server metadata `ssh_user` (per instance, settable on a running server),
2. the image's **`os_admin_user`** property — a standard Glance field, and the
   right place to put it,
3. a guess from the image name / `os_distro`,
4. `--user`, which beats all of the above.

Declare it once per image and every tool benefits, not just nubor:

```bash
openstack image set --property os_admin_user=ubuntu <image>
```

### Ephemeral keys

Cloud-init reads SSH keys **once, at first boot**, and nothing re-reads them
afterwards — so a key added to an instance's metadata later is never seen by the
guest. A resident agent is what makes per-session keys possible.

`guest/nubor-ssh-agent` is that missing piece. With it installed, nubor mints an
ed25519 key per session, publishes it as instance metadata
(`nubor_ssh_<id> = <user>:<expiry>:<key>`), waits for the agent to pick it up,
and revokes it on exit; the embedded expiry is the backstop if that revoke never
happens. No long-lived key, no keypair to distribute.

Install it into an image (or one instance) with the generated cloud-config:

```bash
openstack server create --user-data guest/cloud-config.yaml ...
openstack image set --property nubor_agent=true --property os_admin_user=ubuntu <image>
```

The `nubor_agent=true` marker — on the image, or on the instance — is how nubor
knows injection will actually be picked up; without it, injecting would just
hang. Override either way with `--ephemeral-key` / `--no-ephemeral-key`, and set
the lifetime with `--key-ttl` (default 300s).

The [terraform compute module](https://github.com/nubor-net/terraform-openstack-compute)
installs the agent and sets that marker by default.

### When there is no route to the instance

Not every instance is directly routable from where you are. Reach it through a
jump host, or an identity-aware proxy:

```bash
nubor compute instances ssh web1 --tunnel-through bastion.example   # ssh -J
nubor compute instances ssh-proxy 'cloudflared access ssh --hostname {instance}.ssh.example.net'
nubor compute instances ssh web1        # direct if routable, through the proxy if not
```

`instances ssh` always tries the direct address first and only falls back to the
proxy when there is no route, so instances you can already reach are unaffected.
nubor expands `{instance}` and `{address}`; ssh expands the usual `%h`/`%p`.
`--proxy-command` overrides for one call, `$NUBOR_SSH_PROXY_COMMAND` for one
shell, and `ssh-proxy --clear` forgets the saved one.

The port is checked before anything is minted, so an unreachable address is
reported as unreachable — with the causes worth checking — instead of being
blamed on the guest agent.

## Images and the agent

`nubor compute images list` shows only images marked `nubor_agent=true` — the
ones that can take an ephemeral key. `--all` shows everything, with the property
as a column.

`nubor compute images prune` deletes images carrying neither `nubor_agent=true`
nor `nubor_keep=true`. It lists what will go and prompts (`-q` to skip,
`--dry-run` to stop after the list), and skips any image an instance is booted
from.

Mark your service images first — they are built by their own pipelines, will
never carry the agent, and the cloud loses those services if they go:

```bash
for i in amphora-x64-haproxy manila-service-image trove-guest-ubuntu-noble; do
  openstack image set --property nubor_keep=true "$i"
done
```

Magnum node images (`*-kube-*`) and any golden Windows images want the same
treatment.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e . -r requirements-dev.txt
pytest
ruff check . && ruff format --check .
```

Tests never touch a network; the connection is mocked at the `openstack.connect`
boundary.

`guest/` holds the in-guest agent. `guest/cloud-config.yaml` is **generated** —
run `python guest/build-cloud-config.py` after changing the agent or its unit
file. `python guest/test_agent.py` is a dependency-free self-check for the
agent's parser, runnable from inside a guest where nubor is not installed.
