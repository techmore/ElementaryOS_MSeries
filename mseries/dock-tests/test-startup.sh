#!/usr/bin/env bash
# Compile the actual patched production methods against controlled native services.
set -euo pipefail
ulimit -c 0
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/../.." && pwd)
commit=8b45a68a122947ad3a6427bf6e159ec2acf04ad0
test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT
source_dir=$test_dir/source
mkdir "$source_dir"
if [[ -n ${MSERIES_DOCK_SOURCE:-} ]]; then
    [[ $(git -C "$MSERIES_DOCK_SOURCE" rev-parse HEAD) == "$commit" ]]
    git -C "$MSERIES_DOCK_SOURCE" archive HEAD | tar -x -C "$source_dir"
else
    git -C "$source_dir" init -q
    git -C "$source_dir" fetch -q --depth=1 https://github.com/elementary/dock.git "$commit"
    git -C "$source_dir" checkout -q --detach FETCH_HEAD
fi
git -C "$source_dir" apply "$repo/mseries/patches/dock-drawers.patch"
git -C "$source_dir" apply "$repo/mseries/patches/dock-workspace-startup.patch"
if ! valac --pkg gio-2.0 --directory="$test_dir" --main=ActivationTest.main -o "$test_dir/activation" \
    "$source_dir/src/Application.vala" "$here/activation-stubs.vala" >"$test_dir/activation.log" 2>&1; then
    cat "$test_dir/activation.log" >&2
    exit 1
fi
if ! valac --pkg gio-2.0 --directory="$test_dir" --main=WorkspaceTest.main -o "$test_dir/workspaces" \
    "$source_dir/src/WorkspaceSystem/WorkspaceSystem.vala" "$here/workspace-stubs.vala" >"$test_dir/workspaces.log" 2>&1; then
    cat "$test_dir/workspaces.log" >&2
    exit 1
fi
G_DEBUG=fatal-criticals "$test_dir/activation"
G_DEBUG=fatal-criticals "$test_dir/workspaces"
