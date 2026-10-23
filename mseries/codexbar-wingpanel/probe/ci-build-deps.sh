#!/bin/bash
# Provide granite-7 >= 7.7 and the wingpanel-9 indicator API for building/testing the CodexBar module off
# elementary OS (CI runners, containers). Builds only what pkg-config cannot already satisfy, into PREFIX.
# Wingpanel uses the same pinned commit as install-wingpanel-codexbar-left.sh; only its lib/ is built
# (no compositor or Gala dependencies). Prints KEY=VALUE environment lines on stdout (for $GITHUB_ENV).
#   eval "$(bash ci-build-deps.sh /tmp/prefix | sed 's/^/export /')"
set -euo pipefail
prefix=$(realpath -m "${1:?usage: ci-build-deps.sh PREFIX}")
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
commit=$(sed -n 's/^commit=//p' "$repo/mseries/install-wingpanel-codexbar-left.sh" | head -1)
[[ $commit =~ ^[0-9a-f]{40}$ ]] || { echo "No pinned Wingpanel commit found" >&2; exit 1; }
granite_tag=7.7.0
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

multiarch=$(gcc -dumpmachine 2>/dev/null || echo "")
export PKG_CONFIG_PATH="$prefix/lib/$multiarch/pkgconfig:$prefix/lib/pkgconfig:$prefix/share/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"

if ! pkg-config --atleast-version=7.7.0 granite-7; then
  echo "Building Granite $granite_tag into $prefix" >&2
  git -c advice.detachedHead=false clone -q --depth 1 --branch "$granite_tag" https://github.com/elementary/granite "$work/granite"
  meson setup "$work/granite/build" "$work/granite" --prefix="$prefix" -Ddemo=false -Dintrospection=false >&2
  ninja -C "$work/granite/build" install >&2
fi

if ! pkg-config --exists wingpanel-9; then
  echo "Building the Wingpanel indicator API ($commit) into $prefix" >&2
  git init -q "$work/wingpanel"
  git -C "$work/wingpanel" remote add origin https://github.com/elementary/wingpanel.git
  git -C "$work/wingpanel" fetch -q --depth=1 origin "$commit"
  git -C "$work/wingpanel" checkout -q --detach FETCH_HEAD
  mkdir -p "$work/wplib"
  cp -r "$work/wingpanel/lib" "$work/wplib/lib"
  version=$(sed -n "s/^ *version: *'\([0-9.]*\)'.*/\1/p" "$work/wingpanel/meson.build" | head -1)
  cat > "$work/wplib/meson.build" <<EOF
project('wingpanel', 'vala', 'c', version: '$version')
add_project_arguments('-DGETTEXT_PACKAGE="wingpanel"', language: 'c')
pkg = import('pkgconfig')
glib_dep = dependency('glib-2.0')
gio_dep = dependency('gio-2.0')
gio_unix_dep = dependency('gio-unix-2.0')
gmodule_dep = dependency('gmodule-2.0')
gtk_dep = dependency('gtk4')
gee_dep = dependency('gee-0.8')
granite_dep = dependency('granite-7', version: '>=7.6.0')
subdir('lib')
EOF
  meson setup "$work/wplib/build" "$work/wplib" --prefix="$prefix" >&2
  ninja -C "$work/wplib/build" install >&2
fi

echo "PKG_CONFIG_PATH=$PKG_CONFIG_PATH"
echo "LD_LIBRARY_PATH=$prefix/lib/$multiarch:$prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
echo "XDG_DATA_DIRS=$prefix/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
