#!/usr/bin/env bash
# Build the R0 native packages with the Termux build system (plan R0-2).
#   brotli 1.2.1 (C libraries) and python-brotli 1.2.1: all ABIs
#   python-cffi 2.1.1: aarch64 only
# Dependencies (python, python-pip, libffi) are downloaded from the signed Termux
# apt repository (-i); only the packages above are compiled.
# Usage: scripts/build_native.sh <termux-arch: aarch64|arm|i686|x86_64> <out-dir>
set -euo pipefail
ARCH="$1"; OUT="$(realpath -m "$2")"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCK="$ROOT/inputs.lock"
COMMIT="$(jq -r .build_env.termux_packages.commit "$LOCK")"
IMAGE="$(jq -r .build_env.termux_builder_image "$LOCK")"
TP="$ROOT/work/termux-packages"

rm -rf "$TP"; mkdir -p "$TP"
git -C "$TP" init -q
git -C "$TP" fetch -q --depth 1 https://github.com/termux/termux-packages "$COMMIT"
git -C "$TP" checkout -q FETCH_HEAD
test "$(git -C "$TP" rev-parse HEAD)" = "$COMMIT"

# The pinned recipes must still point at the pinned brotli source.
BROTLI_SHA="$(jq -r .inputs.brotli_source.sha256 "$LOCK")"
for p in brotli python-brotli; do
  grep -q "^TERMUX_PKG_SHA256=$BROTLI_SHA" "$TP/packages/$p/build.sh" || { echo "packages/$p: unexpected source hash"; exit 1; }
  grep -q '^TERMUX_PKG_VERSION="1.2.1"' "$TP/packages/$p/build.sh" || { echo "packages/$p: unexpected version"; exit 1; }
done

mkdir -p "$TP/packages/python-cffi"
sed -e "s|@VERSION@|$(jq -r .inputs.cffi_sdist.version "$LOCK")|" \
    -e "s|@URL@|$(jq -r .inputs.cffi_sdist.url "$LOCK")|" \
    -e "s|@SHA256@|$(jq -r .inputs.cffi_sdist.sha256 "$LOCK")|" \
    "$ROOT/recipes/python-cffi/build.sh" > "$TP/packages/python-cffi/build.sh"

PKGS=(brotli python-brotli)
[ "$ARCH" = aarch64 ] && PKGS+=(python-cffi)

export TERMUX_BUILDER_IMAGE_NAME="$IMAGE"
export CONTAINER_NAME="termux-r0-$ARCH"
export TERMUX_DOCKER_EXEC_EXTRA_ARGS="--env SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1783900800} --env PYTHONDONTWRITEBYTECODE=1"
cd "$TP"
./scripts/run-docker.sh ./build-package.sh -i -a "$ARCH" "${PKGS[@]}"
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

python3 "$ROOT/scripts/collect_native.py" --arch "$ARCH" --debs "$TP/output" --out "$OUT"
