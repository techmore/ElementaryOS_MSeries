#!/bin/sh
# exit 0 = good (PASS), 1 = bad (crash), 125 = skip (build fail / unsupported)
S=/tmp/claude-1000/-home-sdolbec-ElementaryOS-MSeries/1d7ffae4-890b-4bf5-ab8a-e23ad3e40c78/scratchpad
cd $S/mesa-1 || exit 125
nice -n 19 ninja -C build-mlx -j3 >> $S/bisect-build.log 2>&1 || { echo "BUILD FAIL $(git rev-parse --short HEAD)" >> $S/bisect.trace; exit 125; }
out=$(VK_DRIVER_FILES=$S/bisect-icd.json AGX_SIMDMAT=1 MESA_SHADER_CACHE_DISABLE=true timeout 120 $S/cmshape2 16 16 16 f16 f16 f16 f16 row randint 7 16 2>&1); rc=$?
echo "$(git rev-parse --short HEAD) rc=$rc $(echo "$out" | grep -o '"result":"[A-Z]*"')" >> $S/bisect.trace
[ $rc -eq 139 ] && exit 1
echo "$out" | grep -q '"result":"PASS"' && exit 0
exit 125
