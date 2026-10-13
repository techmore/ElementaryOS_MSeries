#!/bin/bash
# Fetch hash-pinned, public Ubuntu Asahi packages needed beside our kernel.
set -euo pipefail
out=${1:?Usage: fetch-asahi-boot-packages.sh PACKAGE_DIRECTORY}
mkdir -p "$out"
: > "$out/UPSTREAM-SHA256SUMS"
base=https://ppa.launchpadcontent.net/ubuntu-asahi/ubuntu-asahi/ubuntu/pool/main
fetch() {
    local path=$1 file=$2 sha=$3
    curl --silent --show-error --fail --location --retry 4 --proto '=https' --tlsv1.2 \
        "$base/$path/$file" --output "$out/$file"
    printf '%s  %s\n' "$sha" "$out/$file" | sha256sum --check --status || {
        rm -f "$out/$file"
        echo "SHA-256 mismatch: $file" >&2
        return 1
    }
    printf '%s  %s\n' "$sha" "$file" >> "$out/UPSTREAM-SHA256SUMS"
}
fetch m/m1n1 m1n1_1.5.2-2ubuntu0.1~asahi1_arm64.deb \
    6c78ead41b46b7cfca145e01743ed4874e58e8b37f0127d46d3b7c186cdb2088
fetch u/u-boot-asahi u-boot-asahi_2025.10-2-1_arm64.deb \
    e0cc3d96dc4d57fb491979280254bc095204588c66984bc46948b35529690b51
