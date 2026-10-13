#!/usr/bin/env bash
# Run from an isolated committed checkout, as the desktop user (sudo must
# already work noninteractively). Builds images only; does not install them.
set -euo pipefail
repo=$(git rev-parse --show-toplevel)
cd "$repo"
records=${LOCAL_BUILD_RECORDS:-$repo/local-build-records}
mkdir -p "$records"
records=$(realpath "$records")
exec > >(tee -a "$records/build.log") 2>&1
source_commit=$(git rev-parse HEAD)
started=$(date +%s)
phase=preflight
write_status() {
    python3 - "$records/status.json" "$1" "$phase" "$source_commit" "$started" "${2:-0}" <<'PY'
import datetime, json, os, pathlib, sys, time
path, state, phase, source, started, code = sys.argv[1:]
data = {'state':state, 'phase':phase, 'sourceCommit':source,
        'startedAt':datetime.datetime.fromtimestamp(int(started),datetime.timezone.utc).isoformat(),
        'updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'elapsedSeconds':int(time.time())-int(started), 'exitCode':int(code)}
p = pathlib.Path(path)
tmp = p.with_suffix('.tmp')
tmp.write_text(json.dumps(data, indent=2)+'\n')
os.replace(tmp,p)
PY
}
finish() {
    code=$?
    trap - EXIT
    if (( code == 0 )); then write_status success "$code"; else write_status failed "$code"; fi
    exit "$code"
}
trap finish EXIT
write_status running
printf 'Source: %s\nRecords: %s\n' "$source_commit" "$records"
python3 mseries/local-build-preflight.py --directory "$repo"
sudo -n true
phase=keygen; write_status running
just genkey
phase=image-build; write_status running
just do-daily
phase=checksum; write_status running
(cd mkosi.output && sha256sum elementaryos-*.iso) | tee "$records/INSTALLER-SHA256SUMS"
phase=complete
