# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project uses [semantic versioning](https://semver.org/spec/v2.0.0.html).
Release notes are generated from the entry for each version, so the headings are
parsed by the release workflow and their format matters.

## [0.7.0] - 2026-08-30

### Added
- `nubor container clusters resize NAME_OR_ID NODE_COUNT` resizes a Magnum
  Kubernetes cluster to the requested worker count, with confirmation by default
  and `-q` for scripts.

## [0.6.2] - 2026-08-24

### Fixed
- `compute instances ssh` now refuses an instance that is not ACTIVE, naming
  the status and pointing at `instances start`. Nova knows the instance is off
  before anything is attempted; finding out by way of a login that fails
  several layers later is the slowest possible way to be told.
- The failure after a login through a proxy or jump host said the instance was
  "reachable, but it never accepted the key". Nothing had checked: the port
  probe is skipped when the route runs through a proxy, so the guest agent was
  being blamed for what may equally have been a proxy that does not reach port
  22. It now says which of the two it cannot distinguish, and only claims the
  instance answered when the probe actually ran.

## [0.6.1] - 2026-08-24

### Fixed
- `container clusters get-credentials` printed a traceback when Magnum refused
  to issue a certificate, which is what a cluster that failed to build does: it
  has no CA to sign against. It now reports the refusal and the cluster's
  status in two lines, like every other failure in the tool.

## [0.6.0] - 2026-08-24

### Added
- `nubor components list` now reports the Keystone, Nova, Glance, Cinder,
  Neutron and Magnum API versions the cloud serves against the versions nubor
  calls, marking each Compatible, Incompatible or Unknown. An update cannot
  raise a cloud's API version, so the mismatch that no upgrade will fix is
  visible before the upgrade. `--only-local-state` contacts neither GitHub nor
  the cloud.

### Fixed
- `nubor container clusters get-credentials` read `tls_disabled` from the
  cluster, where it does not exist, so every call failed with an
  AttributeError. It is a cluster template field, and openstacksdk calls it
  `is_tls_disabled`. 0.5.0 shipped this command without it having been run
  against a live Magnum.

## [0.5.0] - 2026-08-24

### Added

- `nubor components list` reports installed and available versions in a
  gcloud-style component table, with an offline `--only-local-state` mode.
- `nubor components update` installs the latest or a selected release
  through the existing checksum-verifying platform installer.
- `nubor compute instances create --static-private-ip` reserves an
  automatically allocated private address through a persistent Neutron port,
  and `--static-external-ip` automatically allocates and attaches a floating
  IP. Neither option requires choosing an address.
- `nubor container clusters get-credentials`, which writes a kubeconfig entry
  for a Magnum cluster and makes it the current context, the way `gcloud
  container clusters get-credentials` does. The private key is generated
  locally and never sent; Magnum signs a CSR for `admin`/`system:masters`. The
  file is merged, not replaced, and written 0600.

### Changed
- Commands now talk to the Nubor API at `https://api.nubor.net` by default
  instead of calling OpenStack directly, and `nubor auth login` is an OIDC
  device-flow login with MFA whose tokens live in the operating system's
  credential store. `nubor auth logout` revokes the session. The active
  configuration names an API project rather than a `clouds.yaml` entry.
- `--direct` is the break-glass path back to a private OpenStack endpoint, and
  refuses any authentication URL that is not private. Magnum and image deletion
  are only available there.

### Fixed
- The API facade named its Magnum property `container_infrastructure`, which no
  command asks for, so a cluster command against the API endpoint raised an
  AttributeError instead of saying that Magnum needs `--direct`.

## [0.4.0] - 2026-08-22

### Added
- `nubor compute instances start`, `stop` and `reboot`, including `reboot
  --hard` for a power-cycle through Nova.
- `nubor compute flavors list` and `nubor compute networks list` for discovering
  valid inputs before creating an instance.
- `nubor compute instances ssh`, which resolves an instance's address and login
  user from Nova and hands off to the system `ssh`. Everything after the
  instance name is passed through, so `-L`, `-o` and remote commands work.
- Short-lived SSH keys. `guest/nubor-ssh-agent` watches the metadata service
  from inside an instance and maintains a managed block in a user's
  `authorized_keys`; nubor mints an ed25519 key per session, publishes it as
  instance metadata, and revokes it on exit, with an embedded expiry as the
  backstop. Cloud-init reads keys only at first boot, so without the agent a
  key injected later is invisible - which is why this only turns on when the
  instance or image is marked `nubor_agent=true`.
- `--tunnel-through HOST` (`ssh -J`) and `--proxy-command CMD` for instances
  with no route from the client, plus `instances ssh-proxy` to save a standing
  proxy command. A bare `instances ssh` tries the direct address first and falls
  back only when there is none.
- `nubor compute images prune`, which deletes images carrying neither
  `nubor_agent=true` nor `nubor_keep=true`. It prompts, supports `--dry-run`,
  skips images an instance is booted from, and refuses to run when it cannot
  list instances across projects - "unused by me" is not a safe basis for
  deleting a shared image. Mark service images (Octavia amphora, Trove guest,
  Manila, Magnum node images) with `nubor_keep=true` first.

### Changed
- `nubor compute images list` now shows only images marked `nubor_agent=true`,
  the ones that can take an ephemeral key. `--all` restores the old output and
  adds the property as a column.

### Fixed
- `nubor compute instances create --wait` now reports Nova's fault when a server
  enters `ERROR` instead of printing an internal Python traceback.
- The README is valid UTF-8, so source and editable package builds no longer
  fail while reading the package description.

## [0.3.0] - 2026-08-17

### Added
- Binaries for Linux x86_64, macOS arm64 and Windows x86_64, built by CI from the
  release tag and published with a `SHA256SUMS` file.
- Build provenance for every archive, so a download can be checked against the
  workflow and commit that produced it with `gh attestation verify`.
- `scripts/install.sh` and `scripts/install.ps1`, which download the archive for
  the running platform, verify it against `SHA256SUMS`, install it under
  `~/.nubor/versions/<version>` behind a stable entry point, and put it on PATH.
  Re-running upgrades in place, and a build that will not run is rejected before
  it replaces a working one.
- `RELEASING.md` describing how a release is cut and what to check afterwards.

### Changed
- `requires-python` is now `>=3.11`. The previous `>=3.9` was wrong:
  openstacksdk 4.x needs 3.11, and click, tabulate and pytest 9 need 3.10, so
  installing on 3.9 or 3.10 could never have worked. CI now tests 3.11, 3.12
  and 3.13.
- The version is declared once, in `src/nubor/__init__.py`. `pyproject.toml`
  reads it from there, and the release workflow refuses to build when the git tag
  disagrees with it.

### Fixed
- CI was failing on its Python 3.9 job, which is how 0.2.0 came to be released
  from a red build. The job could not have passed; the floor was wrong, not the
  environment.

### Known issues
- The Linux and macOS binaries have not been exercised against a live cloud. The
  PyInstaller spec was only ever built on Windows before this release, and the
  failure mode for a missing plugin import appears on the first API call rather
  than at build time. Installing from source with `pip install .` avoids this.
- The macOS binary is unsigned. Downloading it through a browser applies a
  quarantine attribute; clear it with
  `xattr -d com.apple.quarantine ~/.nubor/bin/nubor`. The installer fetches over
  curl, which does not set the attribute.

## [0.2.0] - 2026-08-17

Tagged but withdrawn. It was released from a failing CI run with a binary built
on a workstation and no checksums, so it could not be verified. 0.3.0 supersedes
it and the release was deleted.

### Added
- Grouped command tree: `compute instances|images|disks`, `container clusters`,
  `config configurations`, `auth`.
- `create` and `delete` for instances, disks and clusters. These resolve every
  referenced resource first, print what was resolved, and prompt before acting.
  Declining exits 1 before any API call is made. `--quiet` skips the prompt.

### Changed
- Restructured from a single script into a src-layout package, one module per
  service group over a shared core.

## [0.1.0] - 2026-08-17

### Added
- Initial prototype: read-only `list` and `describe` for instances, images, disks
  and clusters, named configurations, and table, JSON and YAML output.
