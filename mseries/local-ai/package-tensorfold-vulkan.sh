#!/usr/bin/env bash
# Package the previously built, pinned TensorFold Vulkan server without boot hooks.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=${MSERIES_TENSORFOLD_ROOT:-$HOME/.cache/mseries-tensorfold}
src=$root/src
pin=b3ab9ba217a80c63fcc48f7643ddfe339a8f4bdc
binary=$src/zig-out/native/bin/tensorfold-native-vulkan
[[ $(git -C "$src" rev-parse HEAD) == "$pin" ]] || { echo 'Unexpected TensorFold revision' >&2; exit 1; }
[[ -z $(git -C "$src" status --porcelain --untracked-files=no) ]] || { echo 'TensorFold source has tracked edits' >&2; exit 1; }
[[ -x $binary ]] || { echo 'Build the TensorFold server first' >&2; exit 1; }
out=${1:?usage: package-tensorfold-vulkan.sh NEW_OUTPUT_DEB}
[[ ! -e $out ]] || { echo 'Refusing to overwrite output' >&2; exit 1; }
work=$(mktemp -d "$root/package.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/DEBIAN" "$work/usr/bin" "$work/usr/libexec/mseries" "$work/usr/share/doc/mseries-tensorfold-vulkan"
install -m755 "$binary" "$work/usr/libexec/mseries/tensorfold-native-vulkan"
install -m755 "$here/tensorfold-launcher.sh" "$work/usr/bin/mseries-tensorfold"
cp "$src/LICENSE" "$work/usr/share/doc/mseries-tensorfold-vulkan/copyright"
cp -a "$src/LICENSES" "$work/usr/share/doc/mseries-tensorfold-vulkan/"
printf '%s\n' "$pin" > "$work/usr/share/doc/mseries-tensorfold-vulkan/source-revision"
cat > "$work/DEBIAN/control" <<'CONTROL'
Package: mseries-tensorfold-vulkan
Version: 0.1+git.b3ab9ba-1
Architecture: arm64
Maintainer: ElementaryOS MSeries contributors <builder@localhost>
Depends: libc6, libvulkan1
Section: utils
Priority: optional
Description: TensorFold Vulkan local inference engine for Apple Silicon
 Opt-in Qwen3.5-2B Vulkan engine, built from upstream PR 1544.
CONTROL
dpkg-deb --root-owner-group --build "$work" "$out"
