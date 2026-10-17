#!/usr/bin/env bash
# Hotkey "drawers" for Pantheon: one global shortcut per app that pops it up or
# down and snaps it into a fixed zone of a monitor (a generic Quake-style drawer).
#
#   bash mseries/install-gala-drawers.sh              # build + install into the running Gala
#   bash mseries/install-gala-drawers.sh --revert     # remove the plugin and its schema
#   bash mseries/install-gala-drawers.sh --plugindir DIR
#   bash mseries/install-gala-drawers.sh --vapidir DIR   # reuse an existing Gala checkout
#
# WHY A GALA PLUGIN
#  Gala is a Wayland compositor. It exposes no D-Bus method to move or resize a
#  window (only GrabAccelerator/UngrabAccelerator/ShowOSD at /org/gnome/Shell) and
#  does not implement wlr-layer-shell. The compositor is the only place that can
#  both grab a global hotkey and place an arbitrary window, so this is a plugin.
#
# LOADING
#  Gala's PluginManager is meant to watch its plugin directory and load newly
#  created .so files at runtime, but gala 8.6.2 does not retain the FileMonitor it
#  creates (src/Misc/PluginManager.vala: the monitor is unreferenced and finalized),
#  so the watch is dropped and new plugins only load at the next Gala start. This
#  script still installs the schema before the .so, so a restart picks up both
#  cleanly; the plugin takes effect on the next login (or compositor restart).
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src=$repo/mseries/gala-drawers
plugin=gala-drawers
schema_id=org.pantheon.gala.plugins.drawers
schema_file=$src/$schema_id.gschema.xml

# elementary/gala commit matching the installed gala 8.6.2+r3174, whose vapi/
# directory we need (Gala does not install its mutter/clutter vapi files).
gala_commit=f0791434ac40a50f2aec64700a47b3bb04145752
gala_plugins_prefix=/usr/local/lib/mseries/gala

config_dir=${XDG_CONFIG_HOME:-$HOME/.config}/mseries
config_file=$config_dir/gala-drawers.ini

detect_plugindir() {
  # If the session runs the patched Gala (screen-corners drop-in), use its prefix.
  if [[ -d $gala_plugins_prefix/lib/gala/plugins ]] \
     && ls "$HOME"/.config/systemd/user/io.elementary.gala@wayland.service.d/*.conf >/dev/null 2>&1; then
    echo "$gala_plugins_prefix/lib/gala/plugins"
    return
  fi
  echo "$(pkg-config --variable=libdir gala)/gala/plugins"
}

plugindir=$(detect_plugindir)
vapidir=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --revert)
      sudo rm -f "$plugindir/lib$plugin.so"
      sudo rm -f "/usr/share/glib-2.0/schemas/$schema_id.gschema.xml"
      sudo glib-compile-schemas /usr/share/glib-2.0/schemas
      rm -f "$HOME/.local/bin/mseries-drawers-settings"
      rm -f "$HOME/.local/share/applications/mseries-drawers-settings.desktop"
      echo "Removed the plugin, schema and settings app. It unloads at your next"
      echo "login; your config in $config_file is left in place."
      exit 0 ;;
    --plugindir) plugindir=$2; shift 2 ;;
    --vapidir) vapidir=$2; shift 2 ;;
    *) echo "Unknown option $1" >&2; exit 1 ;;
  esac
done

for tool in git meson ninja valac pkg-config; do
  command -v "$tool" >/dev/null || { echo "Missing $tool." >&2; missing=1; }
done
for mod in gala libmutter-18 gee-0.8 gio-unix-2.0; do
  pkg-config --exists "$mod" 2>/dev/null || { echo "Missing development files for $mod" >&2; missing=1; }
done
if [[ ${missing:-0} == 1 ]]; then
  echo 'Install build requirements with:' >&2
  echo '  sudo apt install git meson ninja-build valac libgala-dev libmutter-18-dev libgee-0.8-dev' >&2
  exit 1
fi

installed_version=$(dpkg-query -W -f='${Version}' gala 2>/dev/null || true)
if [[ $installed_version != 8.6.2* ]]; then
  echo "This plugin targets gala 8.6.2.x; found ${installed_version:-none}." >&2
  exit 1
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/gala-drawers.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT

if [[ -z $vapidir ]]; then
  source_dir=$work_dir/source
  git init -q "$source_dir"
  git -C "$source_dir" remote add origin https://github.com/elementary/gala.git
  git -C "$source_dir" fetch -q --depth=1 origin "$gala_commit"
  git -C "$source_dir" checkout -q --detach FETCH_HEAD
  vapidir=$source_dir/vapi
fi

build_dir=$work_dir/build
meson setup "$build_dir" "$src" --prefix=/usr --buildtype=release \
  -Dvapidir="$vapidir" -Dplugindir="$plugindir" >/dev/null
ninja -C "$build_dir" >/dev/null
test -f "$build_dir/lib$plugin.so"

# 1) Schema first, so the running Gala can read hotkeys the moment the .so lands.
sudo install -Dm0644 "$schema_file" "/usr/share/glib-2.0/schemas/$schema_id.gschema.xml"
sudo glib-compile-schemas /usr/share/glib-2.0/schemas

# 2) Then the plugin. Gala's directory monitor loads it live.
sudo install -Dm0644 "$build_dir/lib$plugin.so" "$plugindir/lib$plugin.so"

# Seed an example config once, without binding any hotkeys by default.
mkdir -p "$config_dir"
if [[ ! -e $config_file ]]; then
  install -m0644 "$src/drawers.ini.example" "$config_file"
  seeded=1
fi

# The settings app (per-user) is the easy way to clear or reassign a drawer.
install -Dm0755 "$src/mseries-drawers-settings" "$HOME/.local/bin/mseries-drawers-settings"
install -Dm0644 "$src/mseries-drawers-settings.desktop" \
  "$HOME/.local/share/applications/mseries-drawers-settings.desktop"
command -v update-desktop-database >/dev/null && \
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true

# Apply the defaults: left Command + N toggles a drawer, Control+Alt+N assigns
# the focused window to it. Skip any slot the user has already customised.
for i in 1 2 3 4 5 6 7 8 9; do
  [[ $(gsettings get "$schema_id" "drawer-$i" 2>/dev/null) == "['<Control>$i']" ]] || \
    gsettings reset "$schema_id" "drawer-$i" 2>/dev/null || true
  gsettings reset "$schema_id" "assign-$i" 2>/dev/null || true
done

echo "Installed lib$plugin.so into $plugindir"
echo "Schema $schema_id compiled."
echo "Installed mseries-drawers-settings (Drawer Shortcuts) for this user."
[[ ${seeded:-0} == 1 ]] && echo "Seeded example config at $config_file"
cat <<EOF

Takes effect at the next Gala start (log out and back in, or restart
io.elementary.gala@wayland.service, which closes your session).

Left Command + 1..9 pops a drawer up/down; Control+Alt+1..9 assigns the focused
window to that drawer (with an on-screen confirmation). Open "Drawer Shortcuts"
to choose apps and zones, or set a hotkey by hand:
  gsettings set $schema_id drawer-1 "['<Control><Alt>t']"
The [drawer-1] group in $config_file controls the app and its zone, and the
plugin reloads it live on save.
Revert:  bash mseries/install-gala-drawers.sh --revert
EOF
