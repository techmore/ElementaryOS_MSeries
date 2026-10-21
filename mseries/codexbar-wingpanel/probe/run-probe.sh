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
printf '#!/usr/bin/env python3\nimport os,pathlib,json,sys\nif sys.argv[1:]==["accounts"]: print((pathlib.Path(os.environ["CB_FIXTURE"]).parent / ("accounts-opencode" + ("-hints" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="hints" else "-single" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="opencode-compact" else "-shared" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="shared-accounts" else "") + ".json")).read_text())\nelse: print(json.dumps({"status":"available","accountEmail":"me@opencode.example","periods":[{"label":"7 days","requests":565,"tokens":120813143,"costUSD":14.72}]}))\n' > "$home/.local/lib/codexbar-cli/codexbar-opencode-local.py"
printf '#!/usr/bin/env python3\nimport os,pathlib\nprint((pathlib.Path(os.environ["CB_FIXTURE"]).parent / ("accounts-codex" + ("-hints" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="hints" else "-shared" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="shared-accounts" else "") + ".json")).read_text())\n' > "$home/.local/lib/codexbar-cli/codexbar-accounts.py"
printf '#!/usr/bin/env python3\nimport os,pathlib\nprint((pathlib.Path(os.environ["CB_FIXTURE"]).parent / ("accounts-claude" + ("-split" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="claude-split" else "-hints" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="hints" else "-shared" if pathlib.Path(os.environ["CB_FIXTURE"]).stem=="shared-accounts" else "") + ".json")).read_text())\n' > "$home/.local/lib/codexbar-cli/codexbar-claude.py"
# Grok Build is a terminal program: a fake CLI plus a terminal launcher that only records what it was asked to run.
mkdir -p "$home/.grok/bin"
printf '#!/bin/sh\nexit 0\n' > "$home/.grok/bin/grok"
printf '#!/bin/sh\nprintf "%%s\\n" "$*" >> "$HOME/terminal.log"\n' > "$home/.local/bin/xdg-terminal-exec"
chmod +x "$home/.grok/bin/grok" "$home/.local/bin/xdg-terminal-exec"
# A real `grok` on PATH (the Grok CLI installer puts ~/.grok/bin there) wins over
# the fixture stub inside grok_binary(), so the panel would launch the real
# binary and the sign-in assertion would not match. Drop every PATH entry that
# provides a grok executable, so the probe is deterministic on any host.
probe_path=""
while IFS= read -r -d ':' dir; do
  [[ -n $dir ]] || continue
  [[ -x $dir/grok ]] && continue
  probe_path="${probe_path:+$probe_path:}$dir"
done < <(printf '%s:' "$PATH")
chmod +x "$home/.local/lib/codexbar-cli/codexbar-claude.py" "$home/.local/lib/codexbar-cli/codexbar-accounts.py" "$home/.local/bin/codexbar-linux" "$home/.local/lib/codexbar-cli/codexbar-sessions.py" "$home/.local/lib/codexbar-cli/codexbar-opencode-local.py"
scenarios=("$@"); [ ${#scenarios[@]} -gt 0 ] || scenarios=(healthy connected hints shared-accounts live depleting exhausted provider-error stale empty busy)
theme=io.elementary.stylesheet.blueberry; [ "$scheme" = dark ] && theme="$theme:dark"
for name in "${scenarios[@]}"; do
  env -i PATH="$home/.local/bin:$probe_path" HOME="$home" LANG=C.UTF-8 GTK_THEME="$theme" GSK_RENDERER=cairo GDK_BACKEND=x11 ${CB_DEBUG:+CB_DEBUG=1} ${CB_HIDE_PANEL:+CB_HIDE_PANEL=1} ${CB_SCROLL:+CB_SCROLL=$CB_SCROLL} ${CB_DIALOG:+CB_DIALOG=$CB_DIALOG} ${CB_PAGE:+CB_PAGE=$CB_PAGE} ${CB_STABILITY:+CB_STABILITY=1} ${CB_ASSERT_LOCAL:+CB_ASSERT_LOCAL=1} ${CB_ASSERT_HIDDEN_TOKENS:+CB_ASSERT_HIDDEN_TOKENS=1} ${CB_ASSERT_DOTS:+CB_ASSERT_DOTS=1} ${CB_ASSERT_GROK:+CB_ASSERT_GROK=1} ${CB_ASSERT_GROK_SIGNIN:+CB_ASSERT_GROK_SIGNIN=1} ${CB_ASSERT_GROK_FREE:+CB_ASSERT_GROK_FREE=1} ${CB_ASSERT_COMPACT:+CB_ASSERT_COMPACT=1} ${CB_ASSERT_LEGEND:+CB_ASSERT_LEGEND=$CB_ASSERT_LEGEND} \
    CB_FIXTURE="$here/fixtures/$name.json" CB_SESSIONS="$here/fixtures/sessions.json" \
    xvfb-run -a -s "-screen 0 800x900x24" "$build/render-probe" "$out/$name${CB_PAGE:+-$CB_PAGE}-$scheme.png" "${CB_DELAY:-3000}"
  echo "rendered $name ($scheme)"
done
