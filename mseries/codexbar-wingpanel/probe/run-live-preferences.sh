#!/bin/bash
# Usage: run-live-preferences.sh BUILD_DIR
set -euo pipefail
build=$(realpath "$1")
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$here/make-fixtures.py" >/dev/null
test_profile=$(mktemp -d)
trap 'rm -rf "$test_profile" 2>/dev/null || true' EXIT
mkdir -p "$test_profile/.local/bin" "$test_profile/.config/codexbar" "$test_profile/.local/lib/codexbar-cli"
printf '{}\n' > "$test_profile/.config/codexbar/wingpanel.json"
cat > "$test_profile/.local/bin/codexbar-linux" <<'SH'
#!/bin/sh
if [ "$1" = --snapshot ]; then
  echo snapshot >> "$TEST_SNAPSHOT_LOG"
  cat "$CB_FIXTURE"
fi
exit 0
SH
chmod +x "$test_profile/.local/bin/codexbar-linux"
for name in accounts claude sessions opencode-local; do
  printf 'print("{\\"accounts\\":[],\\"sessions\\":[]}")\n' > "$test_profile/.local/lib/codexbar-cli/codexbar-$name.py"
done
env -i PATH="$PATH" HOME="$test_profile" XDG_CONFIG_HOME="$test_profile/.config" LANG=C.UTF-8 GTK_THEME=io.elementary.stylesheet.blueberry GSK_RENDERER=cairo GDK_BACKEND=x11 TEST_SNAPSHOT_LOG="$test_profile/snapshots.log" CB_FIXTURE="$here/fixtures/healthy.json" dbus-run-session -- xvfb-run -a "$build/test-live-preferences"
