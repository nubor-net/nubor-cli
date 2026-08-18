#!/usr/bin/env bash
# Installs the nubor client on Linux and macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/nubor-net/nubor-cli/master/scripts/install.sh | bash
#
# Set NUBOR_VERSION to install a specific release rather than the latest.
# Re-running upgrades in place and is safe.

set -euo pipefail

REPO="${NUBOR_REPO:-nubor-net/nubor-cli}"
PREFIX="${NUBOR_HOME:-$HOME/.nubor}"
BASE="https://github.com/${REPO}/releases"
PATH_MARKER="# added by the nubor installer"

TMP=""
cleanup() { [ -n "$TMP" ] && rm -rf "$TMP"; }
trap cleanup EXIT

die() { printf 'error: %s\n' "$1" >&2; exit 1; }
note() { printf '%s\n' "$1"; }

command -v curl >/dev/null 2>&1 || die "curl is required"
command -v tar  >/dev/null 2>&1 || die "tar is required"

# --- platform --------------------------------------------------------------
os="$(uname -s)"
arch="$(uname -m)"

case "$os" in
    Linux)  os_part=linux ;;
    Darwin) os_part=darwin ;;
    *)      die "unsupported operating system: $os (use install.ps1 on Windows)" ;;
esac

case "$arch" in
    x86_64|amd64)  arch_part=x86_64 ;;
    aarch64|arm64) arch_part=arm64 ;;
    *)             die "unsupported architecture: $arch" ;;
esac

# A shell running under Rosetta reports x86_64 on Apple Silicon, and the only
# published macOS build is arm64.
if [ "$os_part" = darwin ] && [ "$arch_part" = x86_64 ]; then
    if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)" = "1" ]; then
        arch_part=arm64
    fi
fi

target="${os_part}-${arch_part}"
case "$target" in
    linux-x86_64|darwin-arm64) ;;
    *) die "no published build for $target (available: linux-x86_64, darwin-arm64). Install from source with 'pip install .'" ;;
esac

# --- resolve the version ---------------------------------------------------
# The latest release redirects to its tag, so the version comes out of the
# redirect rather than needing a JSON parser.
if [ -n "${NUBOR_VERSION:-}" ]; then
    version="${NUBOR_VERSION#v}"
else
    resolved="$(curl -fsSLI -o /dev/null -w '%{url_effective}' "${BASE}/latest")" \
        || die "could not reach ${BASE}/latest"
    version="${resolved##*/tag/v}"
    [ "$version" != "$resolved" ] || die "could not determine the latest version"
fi

# The version becomes a directory name, so constrain it before it reaches a path.
case "$version" in
    *[!0-9A-Za-z.+-]* | "" | .* )
        die "refusing to use '$version' as a version: unexpected characters" ;;
esac

archive="nubor-${version}-${target}.tar.gz"
note "Installing nubor ${version} (${target})"

TMP="$(mktemp -d)"
curl -fsSL -o "$TMP/$archive"   "${BASE}/download/v${version}/${archive}" \
    || die "could not download ${archive} for v${version}"
curl -fsSL -o "$TMP/SHA256SUMS" "${BASE}/download/v${version}/SHA256SUMS" \
    || die "could not download SHA256SUMS for v${version}"

# --- verify ----------------------------------------------------------------
# SHA256SUMS covers every platform, so compare this archive's line rather than
# running -c over the whole file, which would fail on the archives not fetched.
if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$TMP/$archive" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
    actual="$(shasum -a 256 "$TMP/$archive" | awk '{print $1}')"
else
    die "no sha256sum or shasum available to verify the download"
fi

expected="$(awk -v f="$archive" '{ sub(/^\*/, "", $2); if ($2 == f) print $1 }' "$TMP/SHA256SUMS")"
[ -n "$expected" ] || die "SHA256SUMS has no entry for $archive"
[ "$actual" = "$expected" ] || die "checksum mismatch for $archive
  expected $expected
  actual   $actual
Refusing to install."
note "Checksum verified."

# --- install ---------------------------------------------------------------
dest="$PREFIX/versions/$version"
mkdir -p "$dest" "$PREFIX/bin"
tar -C "$dest" -xzf "$TMP/$archive"
[ -f "$dest/nubor" ] || die "archive did not contain the expected binary"
chmod +x "$dest/nubor"

# Run the new binary before it becomes the current one, so a broken download
# leaves any existing installation working.
"$dest/nubor" --version >/dev/null 2>&1 \
    || die "the downloaded binary did not run; leaving the existing installation untouched"

# ln -sfn swaps the link in one step rather than unlink-then-create.
ln -sfn "$dest/nubor" "$PREFIX/bin/nubor"
note "Installed to $PREFIX/bin/nubor"

# --- PATH ------------------------------------------------------------------
shell_name="$(basename "${SHELL:-}")"
case "$shell_name" in
    zsh)  rc="$HOME/.zshrc" ;;
    bash) if [ "$os_part" = darwin ] && [ -f "$HOME/.bash_profile" ]; then
              rc="$HOME/.bash_profile"
          else
              rc="$HOME/.bashrc"
          fi ;;
    fish) rc="$HOME/.config/fish/config.fish" ;;
    *)    rc="" ;;
esac

if [ -n "$rc" ]; then
    mkdir -p "$(dirname "$rc")"
    if [ -f "$rc" ] && grep -Fq "$PATH_MARKER" "$rc"; then
        note "PATH already configured in $rc"
    else
        if [ "$shell_name" = fish ]; then
            printf '\n%s\nfish_add_path "%s/bin"\n' "$PATH_MARKER" "$PREFIX" >> "$rc"
        else
            printf '\n%s\nexport PATH="%s/bin:$PATH"\n' "$PATH_MARKER" "$PREFIX" >> "$rc"
        fi
        note "Added $PREFIX/bin to PATH in $rc"
    fi
else
    note "Could not identify your shell. Add $PREFIX/bin to PATH yourself."
fi

note ""
note "Restart your shell, or run: export PATH=\"$PREFIX/bin:\$PATH\""
note ""
note "To enable command completion, add to your shell startup file:"
case "$shell_name" in
    zsh)  note '  eval "$(_NUBOR_COMPLETE=zsh_source nubor)"' ;;
    fish) note '  _NUBOR_COMPLETE=fish_source nubor | source' ;;
    *)    note '  eval "$(_NUBOR_COMPLETE=bash_source nubor)"' ;;
esac
note ""
note "Run 'nubor --help' to get started."
