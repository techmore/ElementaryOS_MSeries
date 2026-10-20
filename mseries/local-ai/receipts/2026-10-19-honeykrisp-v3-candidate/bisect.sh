#!/bin/sh
# exit 0 = good (PASS), 1 = bad (crash), 125 = skip (build fail / unsupported)
# Usage: MESA_TREE=/path/to/mesa-1 BISECT_DIR=/path/to/bisect-scratch sh bisect.sh
# MESA_TREE contains build-mlx/; BISECT_DIR contains cmshape2 and bisect-icd.json.
set -u

if [ -z "${MESA_TREE:-}" ] || [ -z "${BISECT_DIR:-}" ]; then
  echo "set MESA_TREE and BISECT_DIR (see usage above)" >&2
  exit 125
fi
MESA_TREE=$(cd "$MESA_TREE" 2>/dev/null && pwd) || exit 125
BISECT_DIR=$(cd "$BISECT_DIR" 2>/dev/null && pwd) || exit 125
[ -d "$MESA_TREE/build-mlx" ] || exit 125
[ -x "$BISECT_DIR/cmshape2" ] || exit 125
[ -f "$BISECT_DIR/bisect-icd.json" ] || exit 125

cd "$MESA_TREE" || exit 125
commit=$(git rev-parse --short HEAD) || exit 125
nice -n 19 ninja -C build-mlx -j3 >>"$BISECT_DIR/bisect-build.log" 2>&1 || {
  printf 'BUILD FAIL %s\n' "$commit" >>"$BISECT_DIR/bisect.trace"
  exit 125
}
out=$(env VK_DRIVER_FILES="$BISECT_DIR/bisect-icd.json" AGX_SIMDMAT=1 MESA_SHADER_CACHE_DISABLE=true \
  timeout 120 "$BISECT_DIR/cmshape2" 16 16 16 f16 f16 f16 f16 row randint 7 16 2>&1)
rc=$?
printf '%s rc=%s %s\n' "$commit" "$rc" "$(printf '%s\n' "$out" | grep -o '"result":"[A-Z]*"')" \
  >>"$BISECT_DIR/bisect.trace"
[ "$rc" -eq 139 ] && exit 1
printf '%s\n' "$out" | grep -q '"result":"PASS"' && exit 0
exit 125
