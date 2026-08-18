# Releasing

Releases are built by CI from a tag. Nothing is published from a workstation.

## Cutting a release

1. Make sure `master` is green. A tag pushed onto a failing build produces a
   release nobody can trust, which is how 0.2.0 had to be withdrawn.
2. Update `__version__` in `src/nubor/__init__.py`. That is the only place the
   version is written.
3. Move the changelog's `[Unreleased]` items into a new `## [x.y.z] - YYYY-MM-DD`
   section. The release workflow extracts this section verbatim as the release
   notes and fails if it is missing, so write it for someone deciding whether to
   upgrade.
4. Commit both, and push.
5. Tag and push:

       git tag -a vX.Y.Z -m "vX.Y.Z"
       git push origin vX.Y.Z

## What CI does

`.github/workflows/release.yml` runs on any `v*.*.*` tag:

- **verify** rejects the tag if it does not match `__version__`, or if the
  changelog has no section for it, then runs lint, format and tests. Nothing is
  built unless this passes.
- **build** compiles the binary on Linux, macOS and Windows runners, smoke tests
  each one, and packages it.
- **release** collects all three archives, refuses to continue if any is missing,
  writes `SHA256SUMS`, and creates the GitHub release.

## Afterwards

- Confirm the release has four assets: three archives and `SHA256SUMS`.
- Download one archive and check it yourself rather than trusting the run:

      sha256sum -c SHA256SUMS --ignore-missing

- Run the installer against the new release on at least one platform.

## Tags do not move

Once a tag is pushed it is never re-pointed, even minutes later. Anything already
downloaded keeps its meaning. If a release is wrong, withdraw it and ship the next
version. That is what happened to 0.2.0.

## Artifact provenance

The release workflow attests each archive with `actions/attest-build-provenance`,
which signs a statement that the file came from this workflow at a specific
commit. Anyone can check a download against it:

    gh attestation verify nubor-0.3.0-linux-x86_64.tar.gz --repo nubor-net/nubor-cli

`SHA256SUMS` covers the same ground more simply for anyone without `gh`:

    sha256sum -c SHA256SUMS --ignore-missing

Attestation works because the repository is public. On a private repository it
needs a GitHub Enterprise Cloud plan, and the step fails rather than degrading.
