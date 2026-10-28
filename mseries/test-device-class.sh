#!/bin/bash
# Checks mseries/lib-device.sh: M1 Pro laptop vs M4 mini desktop, from fixtures.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=/dev/null
. "$ROOT/mseries/lib-device.sh"
dt=$(mktemp)
trap 'rm -f "$dt"' EXIT
export ELEMENTARY_DT_COMPATIBLE=$dt
check() { # compatible-entries expected
  printf "$1" >"$dt"
  [[ $(mseries_device_class) == "$2" ]] || { echo "expected $2 for: $1, got $(mseries_device_class)"; exit 1; }
}
check 'apple,j314s\0apple,t6000\0apple,arm-platform\0' laptop
check 'apple,j773g\0apple,t8132\0apple,arm-platform\0' desktop
check 'APPLE,J773G\0' desktop
check 'apple,j773gx\0' laptop
check 'apple,j473\0apple,t8112\0' desktop
check 'qcom,x1e80100\0' unknown
echo "ok: device class (laptop/desktop/unknown)"
