#!/bin/bash
# Estimate kernel build progress: finished compile steps vs. remaining (from a make dry-run).
LOG=${USB4_WORKDIR:-$HOME/fairydust-usb4}/build.log
R=/mnt/fdbuild/root
T=/home/techmore/usb4-pkg/src/linux-fairydust
if grep -q BUILD_PKG_DONE "$LOG"; then echo "100% - build finished"; exit 0; fi
if grep -qE "==> ERROR" "$LOG"; then echo "FAILED:"; grep -E "error:|Error [0-9]" "$LOG" | grep -v rustfmt | head -5; exit 1; fi
done_n=$(grep -cE "^  (CC|CXX|RUSTC|AS|LD|AR|GEN|DTC|HOSTCC)" "$LOG")
rem=$(sudo -n chroot "$R" runuser -l techmore -c "cd $T && make -n -s O=build/base all 2>/dev/null | grep -cE ' -c -o | -o .*\.o '" 2>/dev/null)
rem=${rem:-0}
tot=$((done_n+rem))
pct=$(( tot>0 ? 100*done_n/tot : 0 ))
echo "~${pct}%  ($done_n steps done, ~$rem remaining)  last: $(tail -1 "$LOG" | cut -c1-70)"
