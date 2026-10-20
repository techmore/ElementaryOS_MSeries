#!/usr/bin/env bash
# Install the GPL-3.0 Win11 icon theme (yeyushengfan258/Win11-icon-theme) per user for Windows Work Mode.
# This repository bundles none of the artwork: it is fetched from upstream at install time.
# Upstream licenses it GPL-3.0 (credits Ubuntu's Yaru); its app icons imitate Microsoft's designs.
# Installs Win11 (light) and Win11-dark into ~/.local/share/icons. The themes stay inert until
# selected; Work Mode applies the one named in its icon-theme key while active.
# --uninstall removes both themes (only when this script installed them).
set -euo pipefail

url=https://github.com/yeyushengfan258/Win11-icon-theme.git
commit=a5b460a407da143b32f19a503d7fcebb3edf2371   # 2025-11-14, upstream main
license=GPL-3.0
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons"
themes=(Win11 Win11-dark)
marker=MSERIES-SOURCE

if [[ ${1:-} == --uninstall ]]; then
  for theme in "${themes[@]}"; do
    if [[ -f $icons/$theme/$marker ]]; then
      rm -rf -- "${icons:?}/$theme"
      echo "Removed $icons/$theme"
    elif [[ -e $icons/$theme ]]; then
      echo "Left $icons/$theme alone: it was not installed by this script." >&2
    fi
  done
  echo 'Work Mode falls back to your normal icon theme when the selected theme is missing.'
  exit 0
fi

for command in git gtk-update-icon-cache realpath; do
  command -v "$command" >/dev/null || { echo "Missing dependency: $command" >&2; exit 1; }
done
for theme in "${themes[@]}"; do
  if [[ -e $icons/$theme && ! -f $icons/$theme/$marker ]]; then
    echo "$icons/$theme exists and was not installed by this script; refusing to replace it." >&2
    exit 1
  fi
done

work=$(mktemp -d "${TMPDIR:-/tmp}/mseries-win11-icons.XXXXXX")
trap 'rm -rf "$work"' EXIT
# Downloaded content is untrusted: fetch into its own empty directory, never run its scripts,
# and copy only the icon directories ourselves (this mirrors upstream install.sh at $commit).
src="$work/source"
git init -q "$src"
git -C "$src" remote add origin "$url"
git -C "$src" fetch -q --depth=1 origin "$commit"
git -C "$src" -c advice.detachedHead=false checkout -q --detach FETCH_HEAD
[[ $(git -C "$src" rev-parse HEAD) == "$commit" ]] || { echo 'Fetched the wrong commit.' >&2; exit 1; }
if ! grep -q 'GNU GENERAL PUBLIC LICENSE' "$src/COPYING" || ! grep -q 'Version 3' "$src/COPYING"; then
  echo 'Upstream license is no longer GPL-3.0; review before installing.' >&2
  exit 1
fi

out="$work/out"
mkdir -p "$out"

write_index() {
  local theme=$1
  # Inherit elementary, then hicolor, so icons the theme lacks still resolve (upstream names breeze).
  sed -e "s/^Name=Win11$/Name=$theme/" \
      -e 's/^Comment=.*/Comment=Windows 11-style icons (GPL-3.0, yeyushengfan258\/Win11-icon-theme)/' \
      -e 's/^Inherits=.*/Inherits=elementary,hicolor/' \
      "$src/src/index.theme" > "$out/$theme/index.theme"
  cp "$src/COPYING" "$src/AUTHORS" "$out/$theme/"
  cat > "$out/$theme/$marker" <<EOF
Installed by ElementaryOS_MSeries mseries/install-work-mode-icons.sh
Source: ${url%.git}
Commit: $commit
License: $license (see COPYING; credits in AUTHORS)
EOF
}

scale_links() {
  local dir
  for dir in actions animations apps categories devices emotes emblems mimes places preferences status; do
    ln -sfn "$dir" "$1/$dir@2x"
  done
}

# Light (default) variant.
light="$out/Win11"
mkdir -p "$light/status"
cp -RP "$src"/src/{actions,animations,apps,categories,devices,emotes,emblems,mimes,places,preferences} "$light/"
cp -RP "$src"/src/status/{16,22,24,32,symbolic} "$light/status/"
rm -f "$light"/places/scalable/user-trash{,-full}-dark.svg "$light/places/scalable/.directory"
cp -RP "$src"/links/{actions,apps,categories,devices,emotes,emblems,mimes,places,status,preferences} "$light/"
ln -sfn 32 "$light/preferences/22"
# elementary app ids the theme draws under other names (Win11-dark links to this directory).
for alias in io.elementary.settings:preferences-system io.elementary.photos:photos; do
  [[ -e $light/apps/scalable/${alias%%:*}.svg ]] || ln -s "${alias#*:}.svg" "$light/apps/scalable/${alias%%:*}.svg"
done
write_index Win11
scale_links "$light"

# Dark variant: light glyphs for dark surfaces; everything else links into Win11.
dark="$out/Win11-dark"
mkdir -p "$dark"/{apps,categories,emblems,devices,mimes,places,status}
cp -RP "$src/src/actions" "$dark/"
cp -RP "$src"/src/apps/{22,32,symbolic} "$dark/apps/"
cp -RP "$src"/src/categories/{22,symbolic} "$dark/categories/"
cp -RP "$src/src/emblems/symbolic" "$dark/emblems/"
cp -RP "$src/src/mimes/symbolic" "$dark/mimes/"
cp -RP "$src"/src/devices/{16,22,24,32,symbolic} "$dark/devices/"
cp -RP "$src"/src/places/{16,22,24,scalable,symbolic} "$dark/places/"
cp -RP "$src/src/status/symbolic" "$dark/status/"
mv -f "$dark/places/scalable/user-trash-dark.svg" "$dark/places/scalable/user-trash.svg"
mv -f "$dark/places/scalable/user-trash-full-dark.svg" "$dark/places/scalable/user-trash-full.svg"
rm -f "$dark/places/scalable/.directory"
find "$dark"/{actions,devices,places}/{16,22,24} "$dark"/apps/{22,32} "$dark/categories/22" \
     "$dark"/{actions,devices}/32 "$dark"/{actions,apps,categories,emblems,devices,mimes,places,status}/symbolic \
     -maxdepth 1 -type f -name '*.svg' -exec sed -i 's/#363636/#dedede/g' {} +
cp -RP "$src"/links/actions/{16,22,24,32,symbolic} "$dark/actions/"
cp -RP "$src"/links/devices/{16,22,24,32,symbolic} "$dark/devices/"
cp -RP "$src"/links/places/{16,22,24,scalable,symbolic} "$dark/places/"
cp -RP "$src"/links/apps/{22,symbolic} "$dark/apps/"
cp -RP "$src"/links/categories/{22,symbolic} "$dark/categories/"
cp -RP "$src/links/mimes/symbolic" "$dark/mimes/"
cp -RP "$src/links/status/symbolic" "$dark/status/"
for dir in animations emotes preferences; do ln -sfn "../Win11/$dir" "$dark/$dir"; done
for dir in categories/32 emblems/16 emblems/22 emblems/24 mimes/16 mimes/22 mimes/scalable \
           apps/scalable devices/scalable status/16 status/22 status/24 status/32; do
  ln -sfn "../../Win11/$dir" "$dark/$dir"
done
write_index Win11-dark
scale_links "$dark"

# Keep only regular files and links that stay inside the two installed themes.
while IFS= read -r -d '' link; do
  target=$(realpath -m -- "$link")
  [[ $target == "$out"/* ]] || { echo "Dropping link outside the theme: ${link#"$out"/}" >&2; rm -f -- "$link"; }
done < <(find "$out" -type l -print0)
if find "$out" -type f ! -name '*.svg' ! -name '*.png' ! -name index.theme ! -name COPYING ! -name AUTHORS ! -name "$marker" | grep -q .; then
  echo 'Unexpected non-icon files in the theme; review upstream before installing.' >&2
  exit 1
fi

mkdir -p "$icons"
# Build every cache before moving: Win11-dark's cache must see the Win11 directories it links to.
for theme in "${themes[@]}"; do gtk-update-icon-cache -f -q "$out/$theme"; done
for theme in "${themes[@]}"; do
  rm -rf -- "${icons:?}/$theme"
  mv -- "$out/$theme" "$icons/$theme"
done

echo "Installed ${themes[*]} in $icons (commit ${commit:0:12}, $license)."
echo 'Use it in Windows Work Mode:'
echo '  gsettings set io.elementary.mseries.work-mode icon-theme Win11-dark   # or Win11 for light style'
echo 'Revert: bash mseries/install-work-mode-icons.sh --uninstall'
