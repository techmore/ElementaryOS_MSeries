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
    if os.environ['CB_SWITCH_MODE'] == 'claude-failed-exit':
        print('{"accounts":[]}')
        sys.exit(0)
    print('{"accounts":[{"id":"source|one","email":"source@example.com","active":true},{"id":"target@example.com|two","email":"target@example.com","active":false}]}')
PY
printf 'print("{\\"available\\":false,\\"accounts\\":[],\\"sessions\\":[],\\"periods\\":[]}")\n' > "$profile/.local/lib/codexbar-cli/codexbar-claude.py"
cp "$profile/.local/lib/codexbar-cli/codexbar-claude.py" "$profile/.local/lib/codexbar-cli/codexbar-sessions.py"
cp "$profile/.local/lib/codexbar-cli/codexbar-claude.py" "$profile/.local/lib/codexbar-cli/codexbar-opencode-local.py"
if [[ $mode == claude-failed-exit ]]; then
  cat > "$profile/.local/lib/codexbar-cli/codexbar-claude.py" <<'PYCLAUDE'
import json, os, pathlib, sys
if sys.argv[1] == 'switch':
    pathlib.Path(os.environ['CB_SWITCH_ARGS']).write_text(json.dumps(sys.argv[1:]))
    print('{"ok":true,"message":"Fixture failed after reporting ok"}')
    sys.exit(1)
print('{"available":true,"desktop":{"installed":true},"accounts":[{"number":2,"email":"target@example.com","active":false,"desktopReady":true}]}')
PYCLAUDE
fi
fixture="$here/fixtures/healthy.json"
if [[ $mode == claude-failed-exit ]]; then
  python3 - "$fixture" "$profile/snapshot.json" <<'PYFIXTURE'
import json, sys
data = json.load(open(sys.argv[1]))
data['entries'] = [item for item in data['entries'] if item.get('provider') != 'claude']
with open(sys.argv[2], 'w') as out: json.dump(data, out)
PYFIXTURE
  fixture="$profile/snapshot.json"
fi
expected_error=(); [[ $mode == success ]] || expected_error=(CB_SWITCH_EXPECT_ERROR=1)
env -i PATH="$PATH" HOME="$profile" LANG=C.UTF-8 GTK_THEME=io.elementary.stylesheet.blueberry GSK_RENDERER=cairo GDK_BACKEND=x11 \
  CB_FIXTURE="$fixture" CB_SWITCH_MODE="$mode" CB_SWITCH_ARGS="$profile/args.json" "${expected_error[@]}" \
  dbus-run-session -- xvfb-run -a "$build/test-switch"
python3 - "$profile/args.json" "$mode" <<'PY'
import json, sys
expected = ['switch', '2' if sys.argv[2] == 'claude-failed-exit' else 'target@example.com|two', '--desktop']
assert json.load(open(sys.argv[1])) == expected
print('Exact selected account preserved; real accounts untouched')
PY
