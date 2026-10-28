#!/usr/bin/env bash
# Build the opt-in TensorFold native Vulkan backend (ashhart/TensorFold PR 1517)
# in a private prefix, against our private Honeykrisp ICD. Nothing is installed
# system-wide; the desktop Mesa, the kernel and the MLX workers are untouched.
#
#   tensorfold-vulkan.sh build    fetch the pinned source + Zig, build server and probes
#   tensorfold-vulkan.sh test     GPU-free host suites (no device work)
#   tensorfold-vulkan.sh gpu      stage 1-5 GPU operator gates on the M1 Pro (private ICD only)
#
# Kernel: no change needed. The backend talks to Honeykrisp through the existing
# Asahi DRM UAPI; it requires a Vulkan 1.3 device and wip4's Honeykrisp reports 1.4.
set -euo pipefail

# Pinned inputs. Bump together and re-run all three modes.
TF_REPO=https://github.com/ashhart/TensorFold.git
TF_REF=pull/1517/head
TF_REV=670902196c47f3e70e3f56ab933805713be31aa8
ZIG_VERSION=0.17.0
ZIG_URL=https://ziglang.org/download/0.17.0/zig-aarch64-linux-0.17.0.tar.xz
ZIG_SHA256=9e8d11661d4ae3bd57702a3832781e23ad151dde5798e16a5ccd503f65234ff8

# Never /tmp: it is RAM-backed on this machine.
ROOT=${MSERIES_TENSORFOLD_ROOT:-$HOME/.cache/mseries-tensorfold}
SRC=$ROOT/src
ZIG=$ROOT/zig/zig
ICD=${MSERIES_HK_ICD:-$HOME/.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json}
export ZIG_GLOBAL_CACHE_DIR=$ROOT/zig-global ZIG_LOCAL_CACHE_DIR=$ROOT/zig-local
MIN_FREE_GIB=5

check_disk() {
    local free
    free=$(df --output=avail -BG "$HOME" | tail -1 | tr -dc 0-9)
    if (( free < MIN_FREE_GIB )); then
        echo "refusing: ${free} GiB free under \$HOME, floor is ${MIN_FREE_GIB} GiB" >&2
        exit 1
    fi
}

fetch() {
    mkdir -p "$ROOT"
    if [[ ! -x $ZIG ]] || [[ $("$ZIG" version) != "$ZIG_VERSION" ]]; then
        curl -sSfL -o "$ROOT/zig.tar.xz" "$ZIG_URL"
        echo "$ZIG_SHA256  $ROOT/zig.tar.xz" | sha256sum -c --quiet
        rm -rf "$ROOT/zig" && mkdir -p "$ROOT/zig"
        tar -xJf "$ROOT/zig.tar.xz" -C "$ROOT/zig" --strip-components=1
        rm "$ROOT/zig.tar.xz"
    fi
    [[ -d $SRC/.git ]] || git init -q "$SRC"
    if [[ $(git -C "$SRC" rev-parse -q --verify HEAD 2>/dev/null) != "$TF_REV" ]]; then
        git -C "$SRC" fetch -q --depth 1 "$TF_REPO" "$TF_REF"
        git -C "$SRC" checkout -q --detach FETCH_HEAD
    fi
    local have
    have=$(git -C "$SRC" rev-parse HEAD)
    if [[ $have != "$TF_REV" ]]; then
        echo "PR head moved: have $have, pinned $TF_REV; review the new commits, then bump TF_REV" >&2
        exit 1
    fi
}

zb() { (cd "$SRC" && "$ZIG" build -Dvulkan=true -Doptimize=ReleaseSafe "$@"); }

case ${1:-build} in
build)
    check_disk; fetch
    zb native-vulkan vulkan-model-probe-build vulkan-probe-build \
       stage1-gpu-build stage2-gpu-build stage3-gpu-build stage4-gpu-build stage5-gpu-build
    echo "server: $SRC/zig-out/native/bin  probes: $SRC/zig-out/bin"
    ;;
test)
    check_disk; fetch
    (cd "$SRC" && "$ZIG" build -Dvulkan=true vulkan-host-test qwen35-model-host-test model-host-test)
    ;;
gpu)
    check_disk; fetch
    [[ -f $ICD ]] || { echo "private Honeykrisp ICD not found: $ICD" >&2; exit 1; }
    # Process-local driver selection only. HK_SYSMEM is deliberately left unset:
    # Honeykrisp's default heap (half of RAM) keeps the 6 GiB desktop reserve.
    export VK_DRIVER_FILES=$ICD
    for s in 1 2 3 4 5; do zb "stage${s}-gpu-run"; done
    ;;
*)
    sed -n '2,10p' "$0"; exit 2 ;;
esac
