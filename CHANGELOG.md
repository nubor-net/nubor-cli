# Changelog

## 0.2.0

- Restructured from a single script into a src-layout package with one module
  per service group and a shared core (config, output, errors, confirmation).
- Grouped command tree: `compute instances|images|disks`, `container clusters`,
  `config configurations`, `auth`.
- Added create and delete for instances, disks and clusters. State-changing
  commands print what they resolved and prompt before acting; `--quiet`/`-q`
  skips the prompt. Declining exits 1 before any API call is made.
- Test suite (pytest, mocked connections, no network), ruff lint and format,
  CI running both plus a binary build.
- PyInstaller spec documents the runtime module list the binary needs;
  previously that only existed as a memorized command line.

## 0.1.0

- Single-file prototype: read-only list/describe for instances, images, disks
  and clusters; named configurations; table/json/yaml output.
