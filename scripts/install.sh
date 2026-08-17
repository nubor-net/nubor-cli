#!/usr/bin/env bash
# Installs the nubor client on Linux and macOS.
#
# The repository is private, so every download is authenticated and the release
# asset must be fetched through the API rather than a browser download URL -
# the latter returns 404 without a session.
#
#   GH_TOKEN=... ./install.sh              install the latest release
#   GH_TOKEN=... NUBOR_VERSION=0.3.0 ./install.sh   install a specific version
#
# Re-running upgrades in place and is safe.

set -euo pipefail

REPO="${NUBOR_REPO:-nubor-net/nubor-cli}"
PREFIX="${NUBOR_HOME:-$HOME/.nubor}"
API="https://api.github.com"
PATH_MARKER="# added by the nubor installer"

TMP=""
cleanup() { [ -n "$TMP" ] && rm -rf "$TMP"; }
trap cleanup EXIT

die() { printf 'error: %s\n' "$1" >&2; exit 1; }
note() { printf '%s\n' "$1"; }

# --- prerequisites ---------------------------------------------------------
command -v curl >/dev/null 2>&1 || die "curl is required"
command -v tar  >/dev/null 2>&1 || die "tar is required"

# The asset download redirects from api.github.com to a storage host. curl only
# started stripping Authorization across that hop in 7.58.0; older versions
# forward the token to the redirect target. Refuse rather than leak it.
curl_version="$(curl --version | head -n1 | awk '{print $2}')"
if [ "$(printf '%s\n7.58.0\n' "$curl_version" | sort -V | head -n1)" != "7.58.0" ]; then
    die "curl $curl_version is too old; 7.58.0 or newer is required so the token is not forwarded across the download redirect"
fi

if command -v jq >/dev/null 2>&1; then
    JSON=jq
elif command -v python3 >/dev/null 2>&1; then
    JSON=python3
else
    die "either jq or python3 is required to read the GitHub API response"
fi

# Reads one field out of a release JSON document on stdin.
#   json_field .id            -> release id
#   json_asset_id NAME        -> asset id for the named asset
json_asset_id() {
    local want="$1"
    if [ "$JSON" = jq ]; then
        jq -r --arg n "$want" '.assets[] | select(.name == $n) | .id' 2>/dev/null
    else
        python3 -c '
import json, sys
want = sys.argv[1]
doc = json.load(sys.stdin)
for asset in doc.get("assets", []):
    if asset.get("name") == want:
        print(asset["id"])
        break
' "$want"
    fi
}

json_tag() {
    if [ "$JSON" = jq ]; then
        jq -r '.tag_name' 2>/dev/null
    else
        python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])'
    fi
}

# --- token -----------------------------------------------------------------
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
if [ -z "$TOKEN" ] && command -v gh >/dev/null 2>&1; then
    TOKEN="$(gh auth token 2>/dev/null || true)"
fi
[ -n "$TOKEN" ] || die "no credentials. Set GH_TOKEN to a token with read access to $REPO (fine-grained: Contents read), or run 'gh auth login'"

# curl reads the auth header from stdin rather than argv, so the token never
# appears in the process list.
api() {
    printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" \
        | curl --fail --silent --show-error --location --config - "$@"
}

# --- platform --------------------------------------------------------------
os="$(uname -s)"
arch="$(uname -m)"

case "$os" in
    Linux)  os_part=linux ;;
    Darwin) os_part=darwin ;;
    *)      die "unsupported operating system: $os (this installer covers Linux and macOS; use install.ps1 on Windows)" ;;
esac

case "$arch" in
    x86_64|amd64)  arch_part=x86_64 ;;
    aarch64|arm64) arch_part=arm64 ;;
    *)             die "unsupported architecture: $arch" ;;
esac

target="${os_part}-${arch_part}"
case "$target" in
    linux-x86_64|darwin-arm64) ;;
    *) die "no published build for $target. Available: linux-x86_64, darwin-arm64. Install from source with 'pip install .'" ;;
esac

# --- resolve the release ---------------------------------------------------
if [ -n "${NUBOR_VERSION:-}" ]; then
    release_path="/repos/$REPO/releases/tags/v${NUBOR_VERSION#v}"
else
    release_path="/repos/$REPO/releases/latest"
fi

TMP="$(mktemp -d)"
release_json="$TMP/release.json"

api -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    -o "$release_json" \
    "${API}${release_path}" \
    || die "could not read the release. Check the token has access to $REPO, and that the version exists"

tag="$(json_tag < "$release_json")"
[ -n "$tag" ] && [ "$tag" != null ] || die "could not determine the release tag"
version="${tag#v}"

# The version becomes a directory name, so constrain it before it reaches a path.
case "$version" in
    *[!0-9A-Za-z.+-]* | "" | .* )
        die "refusing to use '$version' as a version: unexpected characters" ;;
esac

archive="nubor-${version}-${target}.tar.gz"
note "Installing nubor ${version} (${target})"

# --- download --------------------------------------------------------------
# Assets on a private repo come from the assets endpoint with an octet-stream
# Accept header. The response redirects to a signed URL; it is never printed,
# because it carries a signature and a bearer JWT.
fetch_asset() {
    local name="$1" dest="$2" id
    id="$(json_asset_id "$name" < "$release_json")"
    [ -n "$id" ] || die "release $tag has no asset named $name"
    api -H "Accept: application/octet-stream" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        -o "$dest" \
        "${API}/repos/$REPO/releases/assets/${id}" \
        || die "failed to download $name"
}

fetch_asset "$archive" "$TMP/$archive"
fetch_asset "SHA256SUMS" "$TMP/SHA256SUMS"

# --- verify ----------------------------------------------------------------
# SHA256SUMS covers every platform's archive, so check this one line rather than
# running -c over the whole file, which would fail on the archives not downloaded.
if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$TMP/$archive" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
    actual="$(shasum -a 256 "$TMP/$archive" | awk '{print $1}')"
else
    die "no sha256sum or shasum available to verify the download"
fi

expected="$(awk -v f="$archive" '{ sub(/^\*/, "", $2); if ($2 == f) print $1 }' "$TMP/SHA256SUMS")"
[ -n "$expected" ] || die "SHA256SUMS has no entry for $archive"

if [ "$actual" != "$expected" ]; then
    die "checksum mismatch for $archive
  expected $expected
  actual   $actual
Refusing to install."
fi
note "Checksum verified."

# --- install ---------------------------------------------------------------
dest="$PREFIX/versions/$version"
mkdir -p "$dest" "$PREFIX/bin"
tar -C "$dest" -xzf "$TMP/$archive"
[ -f "$dest/nubor" ] || die "archive did not contain the expected binary"
chmod +x "$dest/nubor"

# Run the new binary before it becomes the current one. On an upgrade this keeps
# a working install in place if the downloaded build is broken.
"$dest/nubor" --version >/dev/null 2>&1 \
    || die "the downloaded binary did not run; leaving the existing installation untouched"

# ln -sfn replaces the symlink in one step, so an interrupted upgrade leaves the
# previous version in place rather than nothing.
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
    note ""
    note "Restart your shell, or run: export PATH=\"$PREFIX/bin:\$PATH\""
else
    note ""
    note "Could not identify your shell. Add this to its startup file:"
    note "  export PATH=\"$PREFIX/bin:\$PATH\""
fi

# --- completion ------------------------------------------------------------
note ""
note "To enable command completion, add to $([ -n "$rc" ] && echo "$rc" || echo "your shell startup file"):"
case "$shell_name" in
    zsh)  note '  eval "$(_NUBOR_COMPLETE=zsh_source nubor)"' ;;
    fish) note '  _NUBOR_COMPLETE=fish_source nubor | source' ;;
    *)    note '  eval "$(_NUBOR_COMPLETE=bash_source nubor)"' ;;
esac

note ""
note "Run 'nubor --help' to get started."
