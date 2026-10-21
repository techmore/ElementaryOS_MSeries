#!/usr/bin/env bash
# Build the M-series Wingpanel plugin .debs from pinned sources.
# Pilot scope (issue #52): network, quick-settings and the datetime calendar panel.
#
#   OUTDIR=out/mseries-debs bash mseries/debs/build.sh
#
# Inputs (environment):
#   OUTDIR        where finished .debs and SHA256SUMS land (required)
#   REPO_ROOT     repository checkout (default: script's grandparent)
#   ONLY          build just this package (default: all; useful for local checks)
# Layout mirrors mkosi.images/apple-silicon/build-{network-indicator,quick-settings}
# plus the firstboot-only extras from mseries/install-network-throughput.sh.
set -euo pipefail

# Packaging revision: bump when the packaging itself changes (scripts,
# control fields) so apt and dpkg see an upgrade, not a same-version reinstall.
REVISION=0mseries3

OUTDIR=${OUTDIR:?set OUTDIR to the output directory}
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=${REPO_ROOT:-$(cd -- "$HERE/../.." && pwd)}
WORK=$(mktemp -d "${TMPDIR:-/tmp}/mseries-debs.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUTDIR"

record() { printf '%s\n' "$*" >> "$OUTDIR/BUILD-PROVENANCE.txt"; }
: > "$OUTDIR/BUILD-PROVENANCE.txt"
record "source-commit: $(git -C "$ROOT" rev-parse HEAD)"
record "built: $(date -u +%FT%TZ)"

# build_plugin DEB BASE_PKG GATE_PREFIX PLUGIN_PATH MARKER REPO_URL COMMIT [PATCH...] [--] [EXTRA_SETUP]
# EXTRA_SETUP, when present, is a function name run inside the source tree
# after patches (e.g. copying widget sources, running wire scripts).
# Optional per-package hooks, named after the package with - as _:
#   <deb>_files ROOT PKGDIR   install extra files into the package tree
#   <deb>_recommends          print a Recommends: value
build_plugin() {
  local deb=$1 base=$2 gate=$3 plugin_path=$4 marker=$5 repo_url=$6 commit=$7
  shift 7
  if [[ -n ${ONLY:-} && $ONLY != "$deb" ]]; then
    record "$deb: skipped (ONLY=$ONLY)"
    return 0
  fi
  local patches=() extra=""
  while (( $# > 0 )); do
    case $1 in
      --) extra=$2; shift 2 ;;
      *) patches+=("$1"); shift ;;
    esac
  done

  local base_version
  base_version=$(dpkg-query -W -f='${Version}' "$base" 2>/dev/null || true)
  if [[ $base_version != "$gate"* ]]; then
    echo "error: $deb targets $base $gate.x; image has ${base_version:-no package}" >&2
    exit 1
  fi
  record "$deb: base $base $base_version, source $commit"

  local src=$WORK/$deb-source bld=$WORK/$deb-build
  git init -q "$src"
  git -C "$src" remote add origin "$repo_url"
  git -C "$src" fetch -q --depth=1 origin "$commit"
  git -C "$src" checkout -q --detach FETCH_HEAD
  local p
  for p in "${patches[@]}"; do git -C "$src" apply "$ROOT/$p"; done
  if [[ -n $extra ]]; then ( cd "$src" && "$extra" "$ROOT" "$src" ); fi

  # meson and ninja report errors on stdout: keep it in a log, show it on failure.
  local log=$WORK/$deb-build.log
  meson setup "$bld" "$src" --prefix=/usr --libdir=lib/aarch64-linux-gnu \
    --buildtype=release >"$log" 2>&1 || { cat "$log" >&2; echo "error: $deb meson setup failed" >&2; exit 1; }
  ninja -C "$bld" >>"$log" 2>&1 || { tail -n 200 "$log" >&2; echo "error: $deb build failed" >&2; exit 1; }

  local lib=$bld/$plugin_path
  [[ -s $lib ]] || { echo "error: $deb produced no plugin" >&2; exit 1; }
  if ldd "$lib" | grep -q 'not found'; then
    echo "error: $deb has unresolved libraries" >&2; exit 1
  fi
  grep -aqF "$marker" "$lib" || { echo "error: $deb missing marker '$marker'" >&2; exit 1; }

  local pkg=$WORK/$deb-pkg
  rm -rf "$pkg"
  mkdir -p "$pkg/DEBIAN" "$pkg/usr/lib/aarch64-linux-gnu/wingpanel-9"
  install -m 0644 "$lib" "$pkg/usr/lib/aarch64-linux-gnu/wingpanel-9/$(basename "$plugin_path")"
  local hook=${deb//-/_} recommends=""
  if declare -F "${hook}_files" >/dev/null; then "${hook}_files" "$ROOT" "$pkg"; fi
  if declare -F "${hook}_recommends" >/dev/null; then recommends="Recommends: $("${hook}_recommends")"$'\n'; fi
  # The ~ on both bounds matters: elementary daily versions such as
  # 1.4.0~r556 sort below 1.4.0, and 1.4.1~r600 below 1.4.1. Without it the
  # package would reject its own base and accept the next minor's ABI.
  cat > "$pkg/DEBIAN/control" <<EOF
Package: $deb
Version: $gate-$REVISION
Architecture: arm64
Maintainer: techmore <sdolbec1@gmail.com>
Depends: $base (>= $gate~), $base (<< ${gate%.*}.$((${gate##*.} + 1))~)
${recommends}Description: M-series $(basename "$plugin_path" .so) plugin (see issue #52)
 Replaces the stock plugin via dpkg-divert; version-gated to the $gate.x ABI.
EOF
  local soname
  soname=/usr/lib/aarch64-linux-gnu/wingpanel-9/$(basename "$plugin_path")
  cat > "$pkg/DEBIAN/preinst" <<EOF
#!/bin/sh
set -e
if [ "\$1" = install ] || [ "\$1" = upgrade ]; then
  dpkg-divert --package $deb --add --rename \\
    --divert "$soname.mseries-orig" "$soname" >/dev/null
fi
EOF
  # No panel restart here: AGENTS.md keeps the owner's menu bar stable, and an
  # apt upgrade must not reload Wingpanel uninvited. dpkg replaces the plugin by
  # rename, so the running panel keeps the old copy until the next login.
  cat > "$pkg/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
  echo "M-series panel plugin updated; it loads at the next login." >&2
fi
EOF
  cat > "$pkg/DEBIAN/postrm" <<EOF
#!/bin/sh
set -e
if [ "\$1" = remove ] || [ "\$1" = purge ]; then
  dpkg-divert --package $deb --rename --remove "$soname" >/dev/null || true
fi
EOF
  chmod 0755 "$pkg/DEBIAN/preinst" "$pkg/DEBIAN/postinst" "$pkg/DEBIAN/postrm"
  bash -n "$pkg/DEBIAN/preinst"; bash -n "$pkg/DEBIAN/postinst"; bash -n "$pkg/DEBIAN/postrm"
  # Package directories must not inherit the build user's umask.
  find "$pkg" -type d -exec chmod 0755 {} +
  dpkg-deb --build --root-owner-group "$pkg" "$OUTDIR/${deb}_${gate}-${REVISION}_arm64.deb" >/dev/null
  record "$deb: $(cd "$OUTDIR" && sha256sum "${deb}_${gate}-${REVISION}_arm64.deb")"
}

# --- per-package extras ----------------------------------------------------

# Calendar panel: Events/Tasks agenda, Bible tab (daily verse, Titus study).
# The "Calendar Accounts…" item runs this launcher; it opens GNOME Online
# Accounts, which (with EDS) is what actually syncs Google calendars.
mseries_wingpanel_datetime_files() { # ROOT PKGDIR
  install -D -m 0755 "$1/mseries/calendar/accounts" "$2/usr/bin/mseries-calendar-accounts"
}
mseries_wingpanel_datetime_recommends() {
  echo 'evolution-data-server, gnome-online-accounts-gtk, io.elementary.tasks, python3, gh'
}

network_extra() { # ROOT SRC
  git -C "$2" apply --include=data/Indicator.css \
    --include=src/Widgets/UsageWidget.vala \
    --include=src/Widgets/WifiInterface.vala \
    "$1/mseries/netspeed/panel-network.patch"
  python3 "$1/mseries/netspeed/wire-network-usage.py" "$2"
}

quick_extra() { # ROOT SRC: the same patches and widgets as the factory image
  bash "$1/mseries/quick-settings/prepare-source.sh" "$1" "$2"
}

build_plugin mseries-wingpanel-network io.elementary.panel.network 8.0.1 \
  libnetwork.so 'Show speed in menu bar' \
  https://github.com/elementary/panel-network.git \
  8685ec8e55a45e48da0c12931a353cd440d11664 \
  mseries/patches/network-throughput.patch \
  mseries/patches/network-null-devices.patch \
  mseries/patches/network-panel-speed.patch \
  -- network_extra

build_plugin mseries-quick-settings io.elementary.quick-settings 1.4.0 \
  src/libquick-settings.so 'KeyboardBrightness' \
  https://github.com/elementary/quick-settings.git \
  fb721d4b5640a2a25ae011370c8fe8aaff8d93f4 \
  -- quick_extra

# Same pin as the factory image (panel-factory-pins.json), so the two cannot drift.
datetime_commit=$(python3 -c 'import json, sys; print(next(e["commit"] for e in json.load(open(sys.argv[1]))["indicators"] if e["name"] == "datetime"))' "$ROOT/mseries/panel-factory-pins.json")
build_plugin mseries-wingpanel-datetime io.elementary.panel.datetime 2.4.2 \
  libdatetime.so 'verse-of-the-day.ini' \
  https://github.com/elementary/panel-datetime.git \
  "$datetime_commit" \
  mseries/patches/datetime-agenda-tabs.patch

(cd "$OUTDIR" && sha256sum -- ./*.deb | sed 's|\./||' > SHA256SUMS)
echo "built: $(ls "$OUTDIR"/*.deb | wc -l) packages in $OUTDIR"
