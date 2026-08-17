# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project uses [semantic versioning](https://semver.org/spec/v2.0.0.html).
Release notes are generated from the entry for each version, so the headings are
parsed by the release workflow and their format matters.

## [Unreleased]

## [0.3.0] - 2026-08-17

### Added
- Binaries for Linux x86_64, macOS arm64 and Windows x86_64, built by CI from the
  release tag and published with a `SHA256SUMS` file.
- `scripts/install.sh` and `scripts/install.ps1`, which download the archive for
  the running platform, verify it against `SHA256SUMS`, install it under
  `~/.nubor/versions/<version>` behind a stable entry point, and put it on PATH.
  Re-running upgrades in place.
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
