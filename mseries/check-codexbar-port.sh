#!/bin/bash
# Verify our CodexBar custom port still fits the upstream CLI/app. See mseries/CODEXBAR-PORT.md.
#   CODEXBAR_CLI=/path/to/upstream/codexbar bash mseries/check-codexbar-port.sh
set -uo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cli=${CODEXBAR_CLI:-$HOME/.local/lib/codexbar-cli/codexbar-upstream}
fail=0
ok()   { printf 'ok    %s\n' "$1"; }
bad()  { printf 'FAIL  %s\n' "$1"; fail=1; }
note() { printf 'check %s\n' "$1"; }

pin=$(sed -n 's/^version=//p' "$repo/mseries/install-codexbar.sh" | head -1)
have=$("$cli" --version 2>/dev/null | awk '{print $2}')
[[ -n $have ]] && ok "upstream CLI $have (pin $pin)" || bad "upstream CLI not runnable at $cli"
[[ ${pin#v} == "$have" ]] || note "installer pin $pin differs from CLI $have"

for flag in --all-accounts --account; do
  "$cli" --help 2>&1 | grep -q -- "$flag" && ok "CLI supports $flag" || bad "CLI lost $flag"
done
"$cli" usage --provider codex --format json >/dev/null 2>&1 && ok "codex usage runs" || note "codex usage failed (signed out or network)"
empty=$(mktemp -d)
if CODEX_HOME=$empty "$cli" usage --provider codex --format json 2>/dev/null | grep -q '"accountEmail"'; then
  bad "CODEX_HOME is no longer honored (an empty home still reports an account); account switching would break"
else
  ok "CODEX_HOME is honored"
fi
rm -rf "$empty"

# Grok Build (upstream provider since v0.78.0 restored CLI billing): we draw its card, so the id must stay "grok".
if "$cli" config providers --format json 2>/dev/null | grep -q '"provider" *: *"grok"'; then
  ok "CLI lists the grok provider"
else
  bad "CLI no longer lists provider grok; the panel's Grok card and installer order would go stale"
fi
grok_bin=$(command -v grok || true)
for candidate in "${GROK_HOME:-$HOME/.grok}/bin/grok" "$HOME/.local/bin/grok"; do
  [[ -z $grok_bin && -x $candidate ]] && grok_bin=$candidate
done
if [[ -n $grok_bin ]]; then
  if grok_json=$("$cli" usage --provider grok --format json 2>/dev/null) && grep -Eq '"primary" *: *\{' <<<"$grok_json"; then
    ok "grok usage reports a credits window"
  elif grok_json=$("$cli" usage --provider grok --format json 2>/dev/null) && grep -q '"accountEmail"' <<<"$grok_json"; then
    ok "grok is signed in (plan has no credits window; the card says so)"
  else
    note "grok usage returned no credits window (run grok login, or check network)"
  fi
  config="${XDG_CONFIG_HOME:-$HOME/.config}/codexbar/linux.json"
  if python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); sys.exit(0 if c.get("provider")=="custom" and "grok" in c.get("providerOrder",[]) else 1)' "$config" 2>/dev/null; then
    ok "grok is in the panel's provider order"
  else
    note "grok is installed but not in $config providerOrder; rerun install-codexbar.sh or add it in Settings → Providers"
  fi
else
  note "Grok Build is not installed; its card stays hidden"
fi

for f in codexbar-cache codexbar-accounts codexbar-claude codexbar-claude-history codexbar-claude-handoff codexbar-opencode-local codexbar-opencode-login codexbar-sessions; do
  python3 "$repo/mseries/test-$f.py" >/dev/null 2>&1 && ok "tests: $f" || bad "tests: $f"
done
python3 "$repo/mseries/test-codexbar-performance.py" >/dev/null 2>&1 && ok "tests: performance/watch" || bad "tests: performance/watch"
python3 "$repo/mseries/test-codexbar-wrapper.py" >/dev/null 2>&1 && ok "tests: wrapper" || bad "tests: wrapper"
python3 "$repo/mseries/test-codexbar-deploy.py" >/dev/null 2>&1 && ok "tests: deploy/payload" || bad "tests: deploy/payload"

build=$(mktemp -d); trap 'rm -rf "$build"' EXIT
if meson setup "$build" "$repo/mseries/codexbar-wingpanel" >/dev/null 2>&1 && ninja -C "$build" >/dev/null 2>&1 \
   && meson test -C "$build" >/dev/null 2>&1; then ok "Wingpanel module builds, tests pass"; else bad "Wingpanel module build/tests"; fi

app="$HOME/.local/bin/codexbar-linux"
if pgrep -f 'codexbar-linux --background' >/dev/null && snap=$("$app" --snapshot 2>/dev/null); then
  echo "$snap" | python3 -c '
import json, sys
live = json.load(sys.stdin)
fixture = json.load(open(sys.argv[1] + "/mseries/codexbar-wingpanel/probe/fixtures/live.json"))
need = set(fixture) - {"pid"}
missing = need - set(live)
entry_missing = set(fixture["entries"][0]) - set(live["entries"][0]) if live.get("entries") else set()
window_missing = set(fixture["entries"][0]["windows"][0]) - set(live["entries"][0]["windows"][0]) if live.get("entries") and live["entries"][0].get("windows") else set()
print("missing:", sorted(missing), sorted(entry_missing), sorted(window_missing))
sys.exit(1 if (missing or entry_missing or window_missing) else 0)' "$repo" && ok "live --snapshot keys match the panel fixture" || bad "live --snapshot schema drifted from the fixture"
else
  note "CodexBar app not running; start it to compare the live --snapshot schema"
fi
(( fail )) && { echo; echo 'Port check FAILED'; exit 1; } || { echo; echo 'Port check passed (human look still needed for any "check" lines)'; }
