#!/usr/bin/env bash
# Download immutable muvm build sources, or validate an existing cache without
# resetting it. Never repair/delete an owner's modified or unrelated checkout.
mseries_muvm_source() (
    set -euo pipefail
    local url=$1 destination=$2 tag=$3 commit=$4 stage=
    fail() { printf 'muvm source: %s\n' "$*" >&2; exit 1; }
    [[ $commit =~ ^[0-9a-f]{40}$ ]] || fail "invalid immutable commit"
    if [[ -e $destination || -L $destination ]]; then
        [[ ! -L $destination && -d $destination/.git && ! -L $destination/.git ]] \
            || fail "not a standalone source checkout: $destination"
        [[ $(git -C "$destination" remote get-url origin) == "$url" ]] \
            || fail "unexpected origin: $destination"
        [[ $(git -C "$destination" rev-parse HEAD) == "$commit" ]] \
            || fail "unexpected revision: $destination (expected $commit)"
        [[ -z $(git -C "$destination" status --porcelain --untracked-files=all) ]] \
            || fail "modified source cache: $destination; preserve or move it before retrying"
        return
    fi
    stage=$(mktemp -d "${destination}.download.XXXXXX")
    trap '[[ -z $stage ]] || rm -rf -- "$stage"' EXIT
    git -c core.hooksPath=/dev/null clone --quiet --no-checkout --depth 1 --branch "$tag" "$url" "$stage"
    [[ $(git -C "$stage" rev-parse HEAD) == "$commit" ]] \
        || fail "tag $tag does not resolve to expected commit $commit"
    git -c core.hooksPath=/dev/null -C "$stage" checkout --quiet --detach "$commit"
    # Refuse a destination that appeared while downloading.
    mv -T --no-clobber -- "$stage" "$destination"
    [[ ! -e $stage ]] || fail "destination appeared while downloading: $destination"
    stage=
)
