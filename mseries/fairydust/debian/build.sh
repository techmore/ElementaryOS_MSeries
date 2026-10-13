#!/bin/bash
# Build-only native ARM64 Debian packaging of our pinned Fairydust + USB4 source.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
kit="$here/../usb4"
mode=${1:---prepare}
[[ $mode == --prepare || $mode == --build || $mode == --compile ]] || { echo 'Usage: build.sh [--prepare|--build|--compile]' >&2; exit 2; }
: "${FAIRYDUST_WORKDIR:?Set FAIRYDUST_WORKDIR to a private build directory}"
: "${FAIRYDUST_SOURCE_ARCHIVE:?Set FAIRYDUST_SOURCE_ARCHIVE to the pinned source tar.gz}"
[[ $(uname -m) == aarch64 ]] || { echo 'Native ARM64 required' >&2; exit 2; }
[[ $EUID != 0 ]] || { echo 'Run as an ordinary user, not root' >&2; exit 2; }
mkdir -p "$FAIRYDUST_WORKDIR"
work=$(realpath "$FAIRYDUST_WORKDIR")
repo=$(realpath "$here/../../..")
case "$work/" in "$repo/"*) echo 'Build outside the repository' >&2; exit 2;; esac
exec > >(tee -a "$work/build.log") 2>&1
[[ $work != / && $work != "$here" && $work != "$kit" ]] || exit 2
free=$(df -PB1 "$work" | awk 'NR==2 {print $4}')
needed=$((5 * 1024 * 1024 * 1024))
[[ $mode == --prepare ]] || needed=$((40 * 1024 * 1024 * 1024))
[[ $mode != --compile ]] || needed=$((12 * 1024 * 1024 * 1024))
(( free >= needed )) || { echo "Insufficient free space: need $needed bytes" >&2; exit 2; }
check_hash() { printf '%s  %s\n' "$1" "$2" | sha256sum -c -; }
check_hash 20ce358acffff4b3de86201975cd68c7aaf241ae010ec3cca9422bbe2b7f34aa "$FAIRYDUST_SOURCE_ARCHIVE"
check_hash ed53211f0f8378e71e303c7eea5c03e8adbc84ec331392f06d93607ab41ce812 "$kit/config"
check_hash 1b9e6d925cdfe768360880c1d3e10eb0d46ecfe66985b4b9fbf39812c3f9fdfd "$kit/0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch"
src="$work/source"
if [[ $mode != --compile ]]; then
[[ ! -e $src ]] || { echo 'Use a fresh work directory; source already exists' >&2; exit 2; }
mkdir "$src"
tar xzf "$FAIRYDUST_SOURCE_ARCHIVE" --strip-components=1 -C "$src"
cd "$src"
patch --batch --fuzz=0 -p1 < "$kit/0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch"
patch --batch --fuzz=0 -p1 < "$here/0001-runtime-dependencies.patch"
mkdir "$work/output"
out="$work/output"
cp "$kit/config" "$out/.config"
for symbol in TYPEC_DP_ALTMODE TYPEC_NVIDIA_ALTMODE TYPEC_TBT_ALTMODE USB4 USB4_APPLE_SOC RESET_APPLE_CIO; do
    scripts/config --file "$out/.config" --module "$symbol"
done
scripts/config --file "$out/.config" --set-str LOCALVERSION '-elementary-fairydust-usb4' --disable LOCALVERSION_AUTO
make O="$out" olddefconfig
printf '%s\n' ce9f2eba72c061a50b2d790450e90af3439d8c24 > "$work/prepared-source.txt"
else
    [[ -f $work/prepared-source.txt && -f $work/output/.config && -d $src ]] || { echo 'Prepared source/config missing' >&2; exit 2; }
    [[ $(cat "$work/prepared-source.txt") == ce9f2eba72c061a50b2d790450e90af3439d8c24 ]] || exit 2
    out="$work/output"
    cd "$src"
fi
export KBUILD_BUILD_USER=elementary-mseries KBUILD_BUILD_HOST=builder
export KBUILD_BUILD_TIMESTAMP='Mon Oct 12 00:00:00 UTC 2026'
# Keep debug/BTF in the kernel; omit the large separate symbol .deb by default.
if [[ ${FAIRYDUST_DEBUG_PACKAGE:-0} != 1 ]]; then
    export DEB_BUILD_PROFILES="${DEB_BUILD_PROFILES:-} pkg.linux-elementary-fairydust-usb4.nokerneldbg"
fi
if ! grep -Fq 'Depends: kmod, linux-base, initramfs-tools | linux-initramfs-tool' scripts/package/mkdebian; then
    patch --batch --fuzz=0 -p1 < "$here/0001-runtime-dependencies.patch"
fi
if ! grep -Fq 'mkdir -p "${pdir}/usr/lib/linux-image-${KERNELRELEASE}/apple"' scripts/package/builddeb; then
    patch --batch --fuzz=0 -p1 < "$here/0002-precreate-apple-dtb-directory.patch"
fi
export DEBEMAIL=builder@localhost DEBFULLNAME="Elementary MSeries Builder"
export KDEB_CHANGELOG_DIST=resolute
if ! python3 "$here/../../check-kernel-config.py" "$out/.config" --require fairydust > "$work/kernel-config-report.json"; then
    cat "$work/kernel-config-report.json"
    exit 1
fi
make O="$out" -s kernelrelease > "$work/kernelrelease.txt"
cat "$work/kernelrelease.txt"
make O="$out" rustavailable
if [[ $mode == --prepare ]]; then
    echo 'Prepared and config/toolchain checked; kernel not compiled or installed.'
    exit 0
fi
# All available CPUs by default; override for memory/desktop responsiveness.
jobs=${FAIRYDUST_JOBS:-$(nproc)}
[[ $jobs =~ ^[1-9][0-9]*$ ]] || exit 2
cleanup() {
    if [[ -n ${watch_pid:-} ]]; then kill "$watch_pid" 2>/dev/null || true; fi
    if [[ -n ${build_pid:-} ]] && kill -0 "$build_pid" 2>/dev/null; then
        kill -TERM -- "-$build_pid" 2>/dev/null || true
        sleep 5
        kill -KILL -- "-$build_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# The kernel packaging target passes -j1 to dpkg; override it explicitly.
setsid make O="$out" -j "$jobs" bindeb-pkg DPKG_FLAGS="-j$jobs" \
    KDEB_SOURCENAME=linux-elementary-fairydust-usb4 \
    KDEB_PKGVERSION=7.1.13+elementary.usb4.3 LOCALVERSION= &
build_pid=$!
(
    while kill -0 "$build_pid" 2>/dev/null; do
        available=$(df -PB1 "$work" | awk 'NR==2 {print $4}')
        if (( available < 8 * 1024 * 1024 * 1024 )); then
            echo 'Stopping kernel build: less than 8 GiB free' >&2
            kill -TERM -- "-$build_pid" 2>/dev/null || true
            sleep 5
            kill -KILL -- "-$build_pid" 2>/dev/null || true
            exit 1
        fi
        sleep 10
    done
) &
watch_pid=$!
result=0
wait "$build_pid" || result=$?
kill "$watch_pid" 2>/dev/null || true
wait "$watch_pid" 2>/dev/null || true
(( result == 0 )) || exit "$result"
# bindeb-pkg places .deb files in the parent of the output directory.
find "$work" -maxdepth 1 -name '*_7.1.13+elementary.usb4.3_arm64.deb' -print0 | sort -z | xargs -0 -r sha256sum > "$work/debian-packages.txt"
[[ -s $work/debian-packages.txt ]] || { echo 'No Debian packages produced' >&2; exit 1; }
echo 'Built only. Inspect package contents/hooks before any image integration.'
