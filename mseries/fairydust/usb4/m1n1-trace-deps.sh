#!/usr/bin/env bash
# Vendor the two pure-Python dependencies the m1n1 hypervisor proxyclient needs
# (construct, pyserial) without touching the system: no pip, no apt, no sudo.
# Prints the resulting PYTHONPATH and the trace recipe.
#
#   bash mseries/fairydust/usb4/m1n1-trace-deps.sh
#
# See DP-TUNNEL-RE.md section 7. Safe to re-run (idempotent).
set -euo pipefail

M1N1=${M1N1:-$HOME/m1n1-build/m1n1}
DEST=${M1N1_PROXYCLIENT_DEPS:-$HOME/.local/share/m1n1-proxyclient}

[[ -d $M1N1/proxyclient ]] || { echo "m1n1 tree not found at $M1N1 (set M1N1=...)" >&2; exit 2; }

python3 - "$DEST" 'construct==2.10.70' 'pyserial==3.5' <<'PY'
import io, json, os, sys, urllib.request, zipfile

dest, *specs = sys.argv[1:]
os.makedirs(f"{dest}/wheels", exist_ok=True)
os.makedirs(f"{dest}/site", exist_ok=True)


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


for spec in specs:
    pkg, ver = spec.split("==")
    meta = json.loads(fetch(f"https://pypi.org/pypi/{pkg}/{ver}/json"))
    url = next(u["url"] for u in meta["urls"] if u["filename"].endswith(".whl"))
    name = url.rsplit("/", 1)[1]
    data = fetch(url)
    with open(f"{dest}/wheels/{name}", "wb") as fh:
        fh.write(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(f"{dest}/site")
    print(f"vendored {name}")
PY

cat <<EOF

Dependencies vendored in $DEST/site (nothing installed system-wide).

== Trace recipe (run on the SECOND computer) ==
Boot the Mac into m1n1 with the WD22TB4 and its monitor attached, then:

  export PYTHONPATH=$DEST/site:$M1N1/proxyclient

  # 1. DCP / AFK / ASC traffic: EDID, HPD, link config, the dp->tunnel gluing
  python3 $M1N1/proxyclient/tools/run_guest.py \\
    -m $M1N1/proxyclient/hv/trace_dcp.py <m1n1>.macho

  # 2. DPTX PHY MMIO
  python3 $M1N1/proxyclient/tools/run_guest.py \\
    -m $M1N1/proxyclient/hv/trace_dptx.py <m1n1>.macho

<m1n1>.macho comes from the m1n1 build (build/m1n1.macho) or from this Mac's
/boot/m1n1/boot.bin. Look for: the sequence the DCP uses when the dock's DP sink
appears, the remote-port encoding for a tunnelled endpoint, AUX routing, HPD
direction, and the CROSSBAR_ATC_EN / CROSSBAR_MUX_CTRL writes for dpin0/dpin1.
EOF
