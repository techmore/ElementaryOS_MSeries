#!/bin/bash
# Each toolkit gets a separate process, private files/display/bus and synthetic backends.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
output=$(realpath -m "${1:?Usage: run-private-checks.sh OUTPUT}")
mkdir -p "$output"
private=$(mktemp -d)
trap 'rm -rf -- "$private" 2>/dev/null || true' EXIT
mkdir -p "$private"/{home,config,cache,data,runtime}
chmod 700 "$private/runtime"
cat > "$private/bus.conf" <<'BUS'
<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>
BUS
if [[ ! -f /usr/share/themes/io.elementary.stylesheet.blueberry/gtk-4.0/gtk.css ]]; then
  printf '%s\n' 'Elementary stylesheet unavailable: CI checks use GTK Adwaita fallback; release theme acceptance remains open.' > "$output/theme-limit.txt"
fi
for theme in light dark; do
  gtk_theme=io.elementary.stylesheet.blueberry
  [[ $theme != dark ]] || gtk_theme+=:dark
  for scale in 1 2; do
    capture="$output/$theme-scale$scale"
    mkdir -p "$capture"
    for surface in troubleshooter airplay display; do
      case "$surface" in
        troubleshooter) test_path=mseries/local-ai/tests/check-troubleshooter-ui.py ;;
        airplay) test_path=mseries/airplay/tests/check-airplay-ui.py ;;
        display) test_path=mseries/display-settings/test_canvas.py ;;
      esac
      env -i PATH=/usr/bin:/bin LANG=C.UTF-8 HOME="$private/home" \
        XDG_CONFIG_HOME="$private/config" XDG_CACHE_HOME="$private/cache" \
        XDG_DATA_HOME="$private/data" XDG_RUNTIME_DIR="$private/runtime" \
        GTK_THEME="$gtk_theme" GDK_SCALE="$scale" GDK_DPI_SCALE=1 \
        MSERIES_UI_CAPTURE="$capture" MSERIES_DISPLAY_FAKE=1 GSK_RENDERER=cairo GDK_BACKEND=x11 \
        G_DEBUG=fatal-criticals GTK_A11Y=none GIO_USE_VFS=local \
        xvfb-run -a -s '-screen 0 2400x1800x24' dbus-run-session --config-file="$private/bus.conf" -- \
        /usr/bin/python3 "$here/$test_path" -v >"$capture/$surface.log" 2>&1
      printf '%s %s scale%s passed\n' "$surface" "$theme" "$scale"
    done
  done
done

/usr/bin/python3 - "$here" "$output" <<'PY'
import hashlib,json,pathlib,struct,subprocess,sys
root,out=map(pathlib.Path,sys.argv[1:])
paths=['mseries/local-ai/troubleshooter-ui.py','mseries/airplay/mseries-airplay-outputs',
       'mseries/display-settings/mseries-display-settings','mseries/display-settings/test_canvas.py',
       'mseries/display-settings/test-canvas.sh','mseries/ui-audit/run-private-checks.sh',
       'mseries/local-ai/tests/check-troubleshooter-ui.py','mseries/airplay/tests/check-airplay-ui.py']
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
images=[]
for path in sorted(out.glob('*-scale*/*.png')):
    width,height=struct.unpack('>II',path.read_bytes()[16:24])
    images.append({'path':str(path.relative_to(out)),'sha256':sha(path),'pixels':[width,height]})
themes={}
for toolkit in ('3.0','4.0'):
    path=pathlib.Path('/usr/share/themes/io.elementary.stylesheet.blueberry')/('gtk-'+toolkit)/'gtk.css'
    themes[toolkit]=sha(path) if path.exists() else 'unavailable: GTK fallback, no elementary-theme acceptance'
receipt={'source_head':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
         'source_files_sha256':{p:sha(root/p) for p in paths},
         'scope':'Synthetic responsiveness/state and actual scale assertions, private Xvfb; no live accounts, audio, model or display mutations',
         'theme_css_sha256':themes,'toolkit_checks':['GTK3 AirPlay','GTK4 Troubleshooter','GTK3 display canvas'],
         'screen_reader_qualified':False,'images':images}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
