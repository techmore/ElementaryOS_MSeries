#!/bin/bash
# Fake backend only: never closes a real app, switches a real account or restarts Wingpanel.
# Usage: run-switch-probe.sh BUILD_DIR [success|null|array|invalid]
set -euo pipefail
build=$(realpath "$1"); mode=${2:-success}
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
profile=$(mktemp -d)
trap 'rm -rf "$profile" 2>/dev/null || true' EXIT
mkdir -p "$profile/.local/bin" "$profile/.local/lib/codexbar-cli"
python3 "$here/make-fixtures.py" >/dev/null
cat > "$profile/.local/bin/codexbar-linux" <<'SH'
#!/bin/sh
[ "$1" != --snapshot ] || cat "$CB_FIXTURE"
exit 0
SH
chmod +x "$profile/.local/bin/codexbar-linux"
cat > "$profile/.local/lib/codexbar-cli/codexbar-accounts.py" <<'PY'
import json, os, pathlib, sys, time
if sys.argv[1] == 'switch':
    pathlib.Path(os.environ['CB_SWITCH_ARGS']).write_text(json.dumps(sys.argv[1:]))
    time.sleep(.1)
    mode = os.environ['CB_SWITCH_MODE']
    print({'null':'null', 'array':'[]', 'invalid':'not json'}.get(mode, '{"ok":true,"message":"Fixture switched"}'))
else:
    print('{"accounts":[{"id":"source|one","email":"source@example.com","active":true},{"id":"target@example.com|two","email":"target@example.com","active":false}]}')
PY
printf 'print("{\\"available\\":false,\\"accounts\\":[],\\"sessions\\":[],\\"periods\\":[]}")\n' > "$profile/.local/lib/codexbar-cli/codexbar-claude.py"
cp "$profile/.local/lib/codexbar-cli/codexbar-claude.py" "$profile/.local/lib/codexbar-cli/codexbar-sessions.py"
cp "$profile/.local/lib/codexbar-cli/codexbar-claude.py" "$profile/.local/lib/codexbar-cli/codexbar-opencode-local.py"
expected_error=(); [[ $mode == success ]] || expected_error=(CB_SWITCH_EXPECT_ERROR=1)
env -i PATH="$PATH" HOME="$profile" LANG=C.UTF-8 GTK_THEME=io.elementary.stylesheet.blueberry GSK_RENDERER=cairo GDK_BACKEND=x11 \
  CB_FIXTURE="$here/fixtures/healthy.json" CB_SWITCH_MODE="$mode" CB_SWITCH_ARGS="$profile/args.json" "${expected_error[@]}" \
  dbus-run-session -- xvfb-run -a "$build/test-switch"
python3 - "$profile/args.json" <<'PY'
import json, sys
assert json.load(open(sys.argv[1])) == ['switch', 'target@example.com|two', '--desktop']
print('Exact selected account preserved; real accounts untouched')
PY
