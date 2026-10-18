#!/bin/bash
# Render RepoBar fixtures to PNG headlessly (Xvfb + cairo renderer + fake HOME + fake helper).
# Usage: run-probe.sh BUILD_DIR OUT_DIR [light|dark] [scenario...]
set -euo pipefail
build=$(realpath "$1"); out=$2; scheme=${3:-light}; shift 3 || shift $#
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "$out"
python3 "$here/make-fixtures.py"
home=$(mktemp -d); trap 'rm -rf "$home" 2>/dev/null || true' EXIT
mkdir -p "$home/.local/bin" "$home/.cache/mseries/repobar"
cat > "$home/.local/bin/mseries-repobar" <<'HELPER'
#!/bin/sh
case "$1" in
  --refresh|"") cat "$RB_FIXTURE" ;;
  pulls) echo '[{"title":"Add RepoBar render probe","number":12,"html_url":"https://github.com/example/a/pull/12"},{"title":"Fix dock focus on resume","number":11,"html_url":"https://github.com/example/a/pull/11"}]' ;;
  *) echo '[]' ;;
esac
HELPER
chmod +x "$home/.local/bin/mseries-repobar"
scenarios=("$@"); [ ${#scenarios[@]} -gt 0 ] || scenarios=(healthy empty error)
theme=io.elementary.stylesheet.blueberry; [ "$scheme" = dark ] && theme="$theme:dark"
for name in "${scenarios[@]}"; do
  cp "$here/fixtures/$name.json" "$home/.cache/mseries/repobar/snapshot.json"
  env -i PATH="$PATH" HOME="$home" LANG=C.UTF-8 GTK_THEME="$theme" GSK_RENDERER=cairo GDK_BACKEND=x11 \
    XDG_DATA_DIRS="$here/..:/usr/local/share:/usr/share" ${RB_SCOPE:+RB_SCOPE=$RB_SCOPE} ${RB_EXPAND:+RB_EXPAND=1} \
    RB_FIXTURE="$here/fixtures/$name.json" \
    xvfb-run -a -s "-screen 0 800x1000x24" "$build/render-probe" "$out/$name${RB_SCOPE:+-$RB_SCOPE}-$scheme.png" "${RB_DELAY:-2500}"
  echo "rendered $name ($scheme)"
done
