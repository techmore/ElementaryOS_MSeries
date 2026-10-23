#!/usr/bin/env bash
# Run the real indicator against only temporary HOME/fake helper/private D-Bus/Xvfb.
set -euo pipefail
build=$(realpath "$1")
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/bus.conf" <<'BUS'
<busconfig>
  <type>session</type><listen>unix:tmpdir=/tmp</listen>
  <policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy>
</busconfig>
BUS
for mode in race failure; do
  home="$work/$mode"
  mkdir -p "$home/.local/bin" "$home/.config/mseries/repobar" "$home/.cache/mseries/repobar"
  printf 'alice' > "$home/phase"
  printf '{"version":1}' > "$home/.config/mseries/repobar/settings.json"
  printf '{"schemaVersion":1,"account":"disk","repos":[{"name":"DISK_PRIVATE"}]}' > "$home/.cache/mseries/repobar/snapshot.json"
  cat > "$home/.local/bin/mseries-repobar" <<'HELPER'
#!/usr/bin/env python3
import json, pathlib, os, sys, time
phase = (pathlib.Path.home() / 'phase').read_text()
if phase == 'failure':
    print('account unavailable', file=sys.stderr); sys.exit(1)
if phase == 'alice' and os.environ['RB_TEST_MODE'] == 'race': time.sleep(1)
print(json.dumps({'schemaVersion':1, 'host':'github.com', 'account':phase,
 'repos':[{'name':phase.upper()+'_PRIVATE', 'url':'https://example.invalid/repo'}],
 'settings':{'refreshInterval':300}, 'fetchedAt':0}))
HELPER
  chmod +x "$home/.local/bin/mseries-repobar"
  env -i PATH="$PATH" HOME="$home" LANG=C.UTF-8 XDG_CONFIG_HOME="$home/.config" \
    RB_TEST_MODE="$mode" GDK_BACKEND=x11 GSK_RENDERER=cairo GIO_USE_VFS=local GTK_A11Y=none \
    XDG_DATA_DIRS="$home/.local/share" GSETTINGS_SCHEMA_DIR=/usr/share/glib-2.0/schemas \
    xvfb-run -a dbus-run-session --config-file="$work/bus.conf" -- "$build/account-cache-probe"
  echo "account-cache $mode passed"
done
