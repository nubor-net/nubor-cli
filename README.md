# nubor

A command-line client for `https://api.nubor.net`. It authenticates with
Authelia OIDC Device Flow and MFA, stores session material only in the operating
system credential store, and uses project `roger` by default. Direct OpenStack
access remains available only as explicit private-network break glass with
`--direct`. Table output is the default; JSON and YAML are available for scripts.

## Commands

| Command | Backs onto |
|---|---|
| `nubor compute instances list / describe / create / delete / start / stop / reboot / ssh` | Nova |
| `nubor compute flavors list` | Nova |
| `nubor compute networks list` | Neutron |
| `nubor compute images list / prune` | Glance |
| `nubor compute disks list / create / delete` | Cinder |
| `nubor container clusters list / describe / create / delete / get-credentials` | Magnum |
| `nubor config configurations list / activate` | Nubor API project; clouds.yaml with `--direct` |
| `nubor auth login / list / logout` | Authelia OIDC + Nubor API + Keystone |
| `nubor components list / update` | nubor release installer |

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

Once installed, nubor can update itself through the same checksum-verifying
installer:

```bash
nubor components list
nubor components update
```

The list shows the local and latest available versions in a gcloud-style
component table. Pass `--only-local-state` when working offline.

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

nubor never asks for or stores an OpenStack password in normal operation. Login
uses OIDC Device Flow with MFA; OIDC refresh and Keystone tokens remain only in
Credential Manager, Keychain or libsecret, and the session cannot exceed eight
hours.

```bash
nubor config configurations list
nubor config configurations activate roger
nubor auth login
```

For break glass from a private network, configure a private endpoint through
`clouds.yaml` or `OS_*` variables and add `--direct`. The CLI rejects non-private
OpenStack endpoints in this mode.

## Examples

```bash
nubor compute instances list
nubor compute instances create web1 --flavor m1.small --image ubuntu-24.04 --network lan --wait
nubor compute instances create web2 --flavor m1.small --image ubuntu-24.04 --network lan --static-private-ip --static-external-ip
nubor compute instances describe web1 --format json
nubor compute instances stop web1
nubor compute instances start web1
nubor compute instances reboot web1       # add --hard to power-cycle
nubor compute flavors list
nubor compute networks list
nubor compute disks create scratch --size 10
nubor compute disks delete scratch          # prompts; add -q to skip
nubor container clusters list
nubor container clusters get-credentials prod   # writes ~/.kube/config
nubor compute instances ssh web1
nubor compute instances ssh web1 -- -L 8080:localhost:80    # after -- goes to ssh
```

`container clusters get-credentials` does what `gcloud container clusters
get-credentials` does: it writes a kubeconfig entry for the cluster and makes it
the current context, so `kubectl` works straight afterwards. The private key is
generated locally and never leaves the machine - only a certificate signing
request is sent, and Magnum returns a signed client certificate for
`admin`/`system:masters`. The certificate and key are embedded in the
kubeconfig, so the file is the whole credential; it is written with mode 0600
and merged into whatever is already there rather than replacing it. Use
`--kubeconfig` to write elsewhere and `--context` to name the context something
other than the cluster.

`--static-private-ip` creates a persistent Neutron port without specifying an
address. Neutron allocates an address from the subnet pool and DHCP configures
that same fixed address in the guest. The named port is reused when it is free,
so deleting and recreating the instance does not discard the reservation.

`--static-external-ip` allocates and attaches a floating IP without specifying
an address. If the project can see more than one external network, select the
pool with `--external-network NAME`; the address itself is still allocated
automatically. A floating IP is a persistent Neutron NAT resource, not an
address delivered to the guest by DHCP. Using either flag is optional, and the
existing create behavior is unchanged when neither is present.

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
