# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project uses [semantic versioning](https://semver.org/spec/v2.0.0.html).
Release notes are generated from the entry for each version, so the headings are
parsed by the release workflow and their format matters.

## [Unreleased]

### Added

- `nubor components list` reports installed and available versions in a
  gcloud-style component table, with an offline `--only-local-state` mode.
- `nubor components update` installs the latest or a selected release
  through the existing checksum-verifying platform installer.

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
