#!/usr/bin/env bash
# ccache is optional for the native builds (#47): used when installed, a no-op
# when not, and wired in before every meson/cmake configure the first-boot job runs.
# A fake `ccache` on PATH stands in for the real one; nothing is compiled.
set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
fails=0
eq() { if [[ $1 == "$2" ]]; then echo "ok   $3"; else echo "FAIL $3: expected [$1], got [$2]" >&2; fails=$((fails + 1)); fi; }
ok() { local d=$1; shift; if "$@"; then echo "ok   $d"; else echo "FAIL $d" >&2; fails=$((fails + 1)); fi; }

tmp=$(mktemp -d "${TMPDIR:-/tmp}/test-build-ccache.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/with" "$tmp/without"
printf '#!/bin/sh\necho fake ccache\n' >"$tmp/with/ccache"
chmod +x "$tmp/with/ccache"

# probe KIND [ENV...]: what a script sees after mseries_ccache_enable, under `set -eu` like the installers
probe() {
  local path=$1 kind=$2; shift 2
  env -i "PATH=$path" "$@" "$BASH" -c '
    set -eu
    source "$1"
    mseries_ccache_enable "$2" >/dev/null
    mseries_ccache_enable "$2" >/dev/null   # a second call must change nothing
    echo "CC=${CC:-} CXX=${CXX:-} C=${CMAKE_C_COMPILER_LAUNCHER:-} X=${CMAKE_CXX_COMPILER_LAUNCHER:-}"
  ' probe "$here/lib-build.sh" "$kind"
}

eq 'CC=ccache cc CXX=ccache c++ C= X=' "$(probe "$tmp/with:/usr/bin:/bin" meson)" "meson: C and C++ go through ccache, once"
eq 'CC=ccache gcc CXX=ccache c++ C= X=' "$(probe "$tmp/with:/usr/bin:/bin" meson CC=gcc)" "meson: the compiler the caller chose is kept"
eq 'CC=ccache gcc CXX=ccache g++ C= X=' "$(probe "$tmp/with:/usr/bin:/bin" meson 'CC=ccache gcc' CXX=g++)" "meson: an already wrapped compiler is not wrapped again"
eq 'CC= CXX= C=ccache X=ccache' "$(probe "$tmp/with:/usr/bin:/bin" cmake)" "cmake: compiler launchers, CC untouched"
eq 'CC= CXX= C= X=' "$(probe "$tmp/with:/usr/bin:/bin" meson MSERIES_CCACHE=0)" "MSERIES_CCACHE=0 turns it off"
eq 'CC= CXX= C= X=' "$(probe "$tmp/without" meson)" "without ccache nothing changes and nothing fails"
eq 'CC=gcc CXX= C= X=' "$(probe "$tmp/without" meson CC=gcc)" "and the caller's compiler is left alone"

# every build the first-boot job runs enables it before configuring
for script in install-video-decode.sh install-network-throughput.sh install-quick-settings-brightness.sh \
  install-sound-indicator-fix.sh install-keyboard-indicator-fix.sh install-files-portal-fix.sh install-battery-eta.sh; do
  enable=$(grep -n 'mseries_ccache_enable' "$here/$script" | head -1 | cut -d: -f1)
  configure=$(grep -n '^meson setup' "$here/$script" | head -1 | cut -d: -f1)
  ok "$script enables ccache before meson setup" bash -c "[[ -n '$enable' && -n '$configure' && '$enable' -lt '$configure' ]]"
done
enable=$(grep -n 'mseries_ccache_enable cmake' "$here/install-touchegg.sh" | head -1 | cut -d: -f1)
configure=$(grep -n '^cmake -S' "$here/install-touchegg.sh" | head -1 | cut -d: -f1)
ok "install-touchegg.sh enables ccache before cmake" bash -c "[[ -n '$enable' && -n '$configure' && '$enable' -lt '$configure' ]]"
ok "a missing library cannot fail an installer" bash -c "! grep -h 'mseries_ccache_enable' '$here'/install-*.sh | grep -v '|| true'"
for f in lib-build.sh lib-timing.sh modrun.py enhance-modules.json; do
  ok "$f is shipped in the first-boot payload" grep -qw "$f" "$here/enhance.sh"
done

(( fails == 0 )) && echo "all tests passed" || { echo "$fails failure(s)" >&2; exit 1; }
