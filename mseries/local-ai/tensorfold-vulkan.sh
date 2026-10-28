#!/usr/bin/env bash
# Build the opt-in TensorFold native Vulkan backend (ashhart/TensorFold PR 1517)
# in a private prefix, against our private Honeykrisp ICD. Nothing is installed
# system-wide; the desktop Mesa, the kernel and the MLX workers are untouched.
#
#   tensorfold-vulkan.sh build    fetch the pinned source + Zig, build server and probes
#   tensorfold-vulkan.sh test     GPU-free host suites (no device work)
#   tensorfold-vulkan.sh gpu      stage 1-5 GPU operator gates on the M1 Pro (private ICD only)
#   tensorfold-vulkan.sh contract kernel contract (gates 1-5 + planted controls) from PR 1526
#
# Kernel: no change needed. The backend talks to Honeykrisp through the existing
# Asahi DRM UAPI; it requires a Vulkan 1.3 device and wip4's Honeykrisp reports 1.4.
set -euo pipefail

# Pinned inputs. Bump together and re-run all three modes.
TF_REPO=https://github.com/ashhart/TensorFold.git
TF_REF=pull/1517/head
TF_REV=670902196c47f3e70e3f56ab933805713be31aa8
# PR 1526 is the first stacked piece of 1517 (runtime + Q4 projection + kernel contract runner).
TF_CONTRACT_REF=pull/1526/head
TF_CONTRACT_REV=68167f428f3415d1623828fe56c20325dd3a51b1
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
    # Zig 0.17 shows a passing test's stderr under a red "failed command:" header.
    # Only "error:" lines, "'<test>' failed" or a non-zero exit mean a failure.
    if (cd "$SRC" && "$ZIG" build -Dvulkan=true --summary all \
            vulkan-host-test qwen35-model-host-test model-host-test); then
        echo "HOST TESTS: PASS"
    else
        echo "HOST TESTS: FAIL" >&2; exit 1
    fi
    ;;
gpu)
    check_disk; fetch
    [[ -f $ICD ]] || { echo "private Honeykrisp ICD not found: $ICD" >&2; exit 1; }
    # Process-local driver selection only. HK_SYSMEM is deliberately left unset:
    # Honeykrisp's default heap (half of RAM) keeps the 6 GiB desktop reserve.
    export VK_DRIVER_FILES=$ICD
    bin=$SRC/zig-out/bin
    [[ -x $bin/tf-stage5-gpu ]] || { echo "run '$0 build' first" >&2; exit 1; }
    # Honeykrisp reports VK_VENDOR_ID_MESA (0x10005), not Apple's PCI id 0x106b;
    # pinning it refuses any other driver. Probes exit 0 pass, 1 fail, 2 usage,
    # 124 fence timeout; every stage runs regardless.
    failed=0
    for s in 1 2 3 4 5; do
        echo "== stage $s"
        rc=0; "$bin/tf-stage${s}-gpu" --vendor 0x10005 --timeout-ms 60000 || rc=$?
        case $rc in
            0) echo "STAGE $s: PASS" ;;
            124) echo "STAGE $s: GPU TIMEOUT" >&2; failed=1 ;;
            *) echo "STAGE $s: FAIL (exit $rc)" >&2; failed=1 ;;
        esac
    done
    (( failed == 0 )) && echo "GPU GATES: PASS" || { echo "GPU GATES: FAIL" >&2; exit 1; }
    ;;
contract)
    check_disk; fetch
    [[ -f $ICD ]] || { echo "private Honeykrisp ICD not found: $ICD" >&2; exit 1; }
    csrc=$ROOT/src-1526
    if [[ ! -d $csrc ]]; then
        git -C "$SRC" fetch -q --depth 1 "$TF_REPO" "$TF_CONTRACT_REF"
        git -C "$SRC" worktree add -q --detach "$csrc" FETCH_HEAD
    fi
    have=$(git -C "$csrc" rev-parse HEAD)
    [[ $have == "$TF_CONTRACT_REV" ]] || { echo "PR 1526 head moved: have $have, pinned $TF_CONTRACT_REV" >&2; exit 1; }
    (cd "$csrc" && ZIG_LOCAL_CACHE_DIR=$ROOT/zig-local-1526 "$ZIG" build -Dvulkan=true -Doptimize=ReleaseSafe tf-vulkan-kernel-contract)
    export VK_DRIVER_FILES=$ICD
    rc=0; "$csrc/zig-out/bin/tf-vulkan-kernel-contract" || rc=$?
    (( rc == 0 )) && echo "KERNEL CONTRACT: PASS" || { echo "KERNEL CONTRACT: FAIL (exit $rc)" >&2; exit 1; }
    ;;
*)
    sed -n '2,11p' "$0"; exit 2 ;;
esac
