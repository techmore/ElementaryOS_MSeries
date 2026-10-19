#!/bin/bash
# Exercise codexbar_install_cli_compat (lib-codexbar.sh) in a throwaway HOME, the way install-codexbar.sh runs it.
#   bash mseries/test-codexbar-cli-compat.sh CodexBarCLI-vX.Y.Z-linux-aarch64.tar.gz   # real CLI (CI on ARM)
#   bash mseries/test-codexbar-cli-compat.sh                                           # fake CLI linked to libxml2.so.2
# Each case runs once as the installer would and once forced through the private-libxml2 launcher.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
tarball=${1:+$(realpath "$1")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
# shellcheck source=lib-codexbar.sh
source "$here/lib-codexbar.sh"

fake_cli() {  # A real ELF that needs libxml2.so.2 with versioned symbols, like upstream's CLI.
  cat > "$work/fake.c" <<'EOF'
#include <stdio.h>
#include <string.h>
#include <libxml/parser.h>
#include <libxml/xpath.h>
int main(int argc, char **argv) {
  if (argc > 1 && !strcmp(argv[1], "--version")) { puts("CodexBarCLI 0.0.0-fake"); return 0; }
  xmlDocPtr doc = xmlReadMemory("<a><b>grok</b></a>", 18, "x.xml", NULL, 0);
  xmlXPathContextPtr ctx = xmlXPathNewContext(doc);
  xmlXPathObjectPtr result = xmlXPathNodeEval(xmlDocGetRootElement(doc), (const xmlChar *)"string(b)", ctx);
  printf("[{\"provider\":\"%s\"}]\n", (const char *)result->stringval);
  xmlXPathFreeObject(result); xmlXPathFreeContext(ctx); xmlFreeDoc(doc);
  return 0;
}
EOF
  local flags
  read -ra flags <<<"$(pkg-config --cflags --libs libxml-2.0)"
  cc -o "$1/CodexBarCLI" "$work/fake.c" "${flags[@]}"
}

install_cli() {  # Mirrors install-codexbar.sh: extract, then codexbar -> codexbar-upstream.
  local lib="$1/.local/lib/codexbar-cli"
  mkdir -p "$lib"
  if [[ -n $tarball ]]; then
    tar -xzf "$tarball" -C "$lib"
  else
    fake_cli "$lib"
    ln -sf CodexBarCLI "$lib/codexbar"
  fi
  mv -f "$lib/codexbar" "$lib/codexbar-upstream"
}

check_runs() {
  local lib="$1/.local/lib/codexbar-cli" version providers
  version=$(timeout 60 "$lib/codexbar-upstream" --version)
  [[ -n $version ]] || { echo "FAIL: --version printed nothing" >&2; exit 1; }
  if [[ -n $tarball ]]; then
    providers=$(HOME="$1" timeout 60 "$lib/codexbar-upstream" config providers --format json)
  else
    providers=$(timeout 60 "$lib/codexbar-upstream")
  fi
  grep -q '"provider" *: *"grok"' <<<"$providers" || { echo "FAIL: grok missing from: $providers" >&2; exit 1; }
  echo "ok    $2: $version; grok listed"
}

for mode in auto forced; do
  home="$work/$mode"
  install_cli "$home"
  lib="$home/.local/lib/codexbar-cli"
  printf '#!/bin/sh\nexec "$0" "$@"\n' > "$lib/codexbar-upstream.real"   # leftover from an earlier broken attempt
  CODEXBAR_FORCE_LIBXML2_COMPAT=$([[ $mode == forced ]] && echo 1 || echo 0) codexbar_install_cli_compat "$lib"
  [[ ! -e "$lib/codexbar-upstream.real" ]] || { echo "FAIL: stale launcher state kept" >&2; exit 1; }
  if [[ -f "$lib/CodexBarCLI.bin" ]]; then
    grep -q 'CodexBarCLI.bin' "$lib/CodexBarCLI" || { echo "FAIL: launcher does not target the binary" >&2; exit 1; }
    readelf -d "$lib/compat/libxml2.so.2" | grep -q 'SONAME.*libxml2.so.2' || { echo "FAIL: compat soname" >&2; exit 1; }
    if readelf -d "$lib/compat/libxml2.so.2" | grep -E 'NEEDED' | grep -v -E 'libc\.so|libm\.so' | grep -q .; then
      echo "FAIL: compat libxml2 pulls extra libraries" >&2; exit 1
    fi
    LD_DEBUG=libs timeout 60 "$lib/codexbar-upstream" --version 2>&1 >/dev/null \
      | grep -q "calling init: $lib/compat/libxml2.so.2" \
      || { echo "FAIL: the launcher did not load the private libxml2" >&2; exit 1; }
    echo "ok    $mode: private libxml2 $(cat "$lib/compat/libxml2.commit") loaded through the launcher"
  else
    echo "ok    $mode: system provides libxml2.so.2; CLI installed unchanged"
  fi
  check_runs "$home" "$mode"
  # Re-install over the launcher, as the next install-codexbar.sh run does: still loads, never self-execs.
  install_cli "$home"
  CODEXBAR_FORCE_LIBXML2_COMPAT=$([[ $mode == forced ]] && echo 1 || echo 0) codexbar_install_cli_compat "$lib"
  check_runs "$home" "$mode reinstall"
done

# A launcher script in place of the binary must be refused, not wrapped (the 2026-10-19 self-exec loop).
home="$work/refuse"
install_cli "$home"
printf '#!/bin/sh\nexec "$0" "$@"\n' > "$home/.local/lib/codexbar-cli/CodexBarCLI"
if codexbar_install_cli_compat "$home/.local/lib/codexbar-cli" 2>/dev/null; then
  echo "FAIL: a non-ELF CodexBarCLI was accepted" >&2; exit 1
fi
echo "ok    refuses to wrap a CodexBarCLI that is not the upstream binary"
