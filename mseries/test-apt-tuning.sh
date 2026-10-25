#!/usr/bin/env bash
# Install the tuning module into a scratch root and check apt accepts and applies the speed settings.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(mktemp -d)
trap 'rm -rf -- "$root"' EXIT
mkdir -p "$root/var/lib/man-db" && touch "$root/var/lib/man-db/auto-update"
bash "$here/enhance.sh" --root "$root" --only tuning >/dev/null
[[ ! -e $root/var/lib/man-db/auto-update ]] || { echo 'FAIL man-db auto-update flag not removed'; exit 1; }
conf=$root/etc/apt/apt.conf.d/90-mseries-speed
[[ -f $conf ]] || { echo 'FAIL apt speed config not installed'; exit 1; }
dump=$(APT_CONFIG=$conf apt-config dump)
for want in 'Acquire::Languages:: "none";' 'Acquire::PDiffs "false";' 'Acquire::Retries "3";' 'DPkg::Lock::Timeout "120";'; do
  grep -qxF "$want" <<<"$dump" || { echo "FAIL apt does not report: $want"; exit 1; }
done
# Idempotent re-run.
bash "$here/enhance.sh" --root "$root" --only tuning >/dev/null
echo 'APT tuning tests passed'
