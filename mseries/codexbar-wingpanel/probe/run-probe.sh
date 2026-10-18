#!/bin/bash
# Render every fixture scenario to PNG headlessly (Xvfb + cairo renderer + fake HOME + fake backend).
# Usage: run-probe.sh BUILD_DIR OUT_DIR [dark|light] [scenario...]
set -euo pipefail
build=$(realpath "$1"); out=$2; scheme=${3:-light}; shift 3 || shift $#
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "$out"
python3 "$here/make-fixtures.py" >/dev/null
home=$(mktemp -d); trap 'rm -rf "$home" 2>/dev/null || true' EXIT
mkdir -p "$home/.local/bin" "$home/.local/lib/codexbar-cli"
if [[ -n ${CB_DISPLAY_PREFS:-} ]]; then
  mkdir -p "$home/.config/codexbar"
  cp -- "$CB_DISPLAY_PREFS" "$home/.config/codexbar/wingpanel.json"
fi
printf '#!/bin/sh\n[ "$1" = --snapshot ] && cat "$CB_FIXTURE"\nexit 0\n' > "$home/.local/bin/codexbar-linux"
printf '#!/usr/bin/env python3\nimport os,sys\nsys.stdout.write(open(os.environ["CB_SESSIONS"]).read())\n' > "$home/.local/lib/codexbar-cli/codexbar-sessions.py"
printf '#!/usr/bin/env python3\nimport os,pathlib,json,sys\nif sys.argv[1:]==["accounts"]: print((pathlib.Path(os.environ["CB_FIXTURE"]).parent / ("accounts-opencode" + ("-hints" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="hints" else "-single" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="opencode-compact" else "") + ".json")).read_text())\nelse: print(json.dumps({"status":"available","accountEmail":"me@opencode.example","periods":[{"label":"7 days","requests":565,"tokens":120813143,"costUSD":14.72}]}))\n' > "$home/.local/lib/codexbar-cli/codexbar-opencode-local.py"
printf '#!/usr/bin/env python3\nimport os,pathlib\nprint((pathlib.Path(os.environ["CB_FIXTURE"]).parent / ("accounts-codex" + ("-hints" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="hints" else "") + ".json")).read_text())\n' > "$home/.local/lib/codexbar-cli/codexbar-accounts.py"
printf '#!/usr/bin/env python3\nimport os,pathlib\nprint((pathlib.Path(os.environ["CB_FIXTURE"]).parent / ("accounts-claude" + ("-hints" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="hints" else "") + ".json")).read_text())\n' > "$home/.local/lib/codexbar-cli/codexbar-claude.py"
chmod +x "$home/.local/lib/codexbar-cli/codexbar-claude.py" "$home/.local/lib/codexbar-cli/codexbar-accounts.py" "$home/.local/bin/codexbar-linux" "$home/.local/lib/codexbar-cli/codexbar-sessions.py" "$home/.local/lib/codexbar-cli/codexbar-opencode-local.py"
scenarios=("$@"); [ ${#scenarios[@]} -gt 0 ] || scenarios=(healthy connected hints live depleting exhausted provider-error stale empty busy)
theme=io.elementary.stylesheet.blueberry; [ "$scheme" = dark ] && theme="$theme:dark"
for name in "${scenarios[@]}"; do
  env -i PATH="$PATH" HOME="$home" LANG=C.UTF-8 GTK_THEME="$theme" GSK_RENDERER=cairo GDK_BACKEND=x11 ${CB_DEBUG:+CB_DEBUG=1} ${CB_HIDE_PANEL:+CB_HIDE_PANEL=1} ${CB_SCROLL:+CB_SCROLL=$CB_SCROLL} ${CB_DIALOG:+CB_DIALOG=$CB_DIALOG} ${CB_PAGE:+CB_PAGE=$CB_PAGE} ${CB_STABILITY:+CB_STABILITY=1} ${CB_ASSERT_LOCAL:+CB_ASSERT_LOCAL=1} ${CB_ASSERT_HIDDEN_TOKENS:+CB_ASSERT_HIDDEN_TOKENS=1} ${CB_ASSERT_DOTS:+CB_ASSERT_DOTS=1} \
    CB_FIXTURE="$here/fixtures/$name.json" CB_SESSIONS="$here/fixtures/sessions.json" \
    xvfb-run -a -s "-screen 0 800x900x24" "$build/render-probe" "$out/$name${CB_PAGE:+-$CB_PAGE}-$scheme.png" "${CB_DELAY:-3000}"
  echo "rendered $name ($scheme)"
done
