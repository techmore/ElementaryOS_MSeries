#!/usr/bin/env bash
# Build OpenCode Desktop (Electron, anomalyco/opencode branch v2) for arm64 and
# repack the .deb with Ubuntu 26.04 t64 dependency names.
#   bash mseries/opencode-desktop/build-opencode-desktop.sh            # build + repack
#   bash mseries/opencode-desktop/build-opencode-desktop.sh --install  # also apt install
# Upstream publishes only an amd64 .deb; this is the arm64 port. Work dir:
# ${OPENCODE_SRC:-$HOME/src/opencode-v2}. Output: $OPENCODE_SRC/opencode-dev-arm64.deb
set -euo pipefail
src=${OPENCODE_SRC:-$HOME/src/opencode-v2} ref=${OPENCODE_REF:-v2}
export PATH=$HOME/.bun/bin:$PATH
if ! command -v bun >/dev/null; then
  curl -fsSL https://bun.sh/install | bash -s "bun-v1.4.2"
fi
if [[ ! -d $src/.git ]]; then
  git clone --depth 1 --branch "$ref" https://github.com/anomalyco/opencode.git "$src"
fi
rev=$(git -C "$src" rev-parse --short HEAD)
cd "$src" && bun install
cd packages/desktop && bun run prebuild && bun run build
bunx electron-builder --linux deb --config electron-builder.config.ts
deb=$src/packages/desktop/dist/opencode-desktop-linux-arm64.deb
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
dpkg-deb -R "$deb" "$work/x"
# Ubuntu 26.04 renamed these to t64; upstream control still lists the old names.
sed -i -E 's/\blibgtk-3-0\b/libgtk-3-0t64/; s/\blibatspi2\.0-0\b/libatspi2.0-0t64/' "$work/x/DEBIAN/control"
out=$src/opencode-dev-arm64.deb
dpkg-deb -b "$work/x" "$out" >/dev/null
echo "Built $out from anomalyco/opencode@$rev"
[[ ${1:-} == --install ]] && sudo apt-get install -y "$out"
exit 0
