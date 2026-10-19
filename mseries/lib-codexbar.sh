# shellcheck shell=bash
# Shared CodexBar port payload. Sourced by install-codexbar.sh, install-codexbar-wingpanel.sh and
# deploy-codexbar.sh so the helper set cannot drift between them. enhance.sh copies the same files
# into the image; test-codexbar-deploy.py checks that list and every helper's local imports against this one.

# Python helpers installed into ~/.local/lib/codexbar-cli (modules use _, executables use -).
CODEXBAR_HELPERS=(
  codexbar_cache.py
  codexbar_tokens.py
  codexbar_history.py
  codexbar_claude_history.py
  codexbar_claude_handoff.py
  codexbar-sessions.py
  codexbar-accounts.py
  codexbar-claude.py
  codexbar-opencode-local.py
  codexbar-opencode-login.py
  codexbar-wingpanel-watch.py
)

# Provider marks installed as mseries-codexbar-<name>-symbolic.svg (read by the sourcing scripts).
# shellcheck disable=SC2034
CODEXBAR_MARKS=(openai claude opencode grok)

# codexbar_install_helpers REPO: install every helper; executables 0755, imported modules 0644.
codexbar_install_helpers() {
  local repo=$1 lib="$HOME/.local/lib/codexbar-cli" helper mode
  mkdir -p "$lib"
  for helper in "${CODEXBAR_HELPERS[@]}"; do
    mode=0755
    [[ $helper == *_* && $helper != *-* ]] && mode=0644
    install -m "$mode" "$repo/mseries/$helper" "$lib/$helper"
  done
}

# Upstream's Linux CLI (v0.78.0+) links libxml2.so.2; libxml2 2.14+ bases ship only libxml2.so.16
# (a soname change for real ABI breaks, so a symlink is not safe). When the CLI cannot resolve it,
# build the last .so.2 series privately: no ICU/lzma/zlib/Python, only libc/libm, with upstream's
# symbol-version script so every LIBXML2_x.y reference resolves exactly. Nothing system-wide changes.
CODEXBAR_LIBXML2_TAG=v2.13.9
CODEXBAR_LIBXML2_COMMIT=04af2cabb9f859c198b8a553c028a87481199410
CODEXBAR_LIBXML2_REPO=https://github.com/GNOME/libxml2.git

# codexbar_cli_missing_libs LIB: print the CLI's unresolved shared libraries (empty when it can load).
codexbar_cli_missing_libs() {
  local binary="$1/CodexBarCLI"
  [[ -f "$1/CodexBarCLI.bin" ]] && binary="$1/CodexBarCLI.bin"
  LD_LIBRARY_PATH="$1/compat${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ldd "$binary" 2>/dev/null \
    | awk '/=> not found/ {print $1}'
}

# codexbar_install_cli_compat LIB: make a freshly extracted CLI loadable on this base.
# Must run right after the CLI tarball is extracted into LIB (CodexBarCLI is then the real ELF binary).
# CODEXBAR_FORCE_LIBXML2_COMPAT=1 exercises the build/launcher path even where the system has .so.2 (CI).
codexbar_install_cli_compat() {
  local lib=$1 missing work stamp="$1/compat/libxml2.commit"
  if [[ $(head -c 4 "$lib/CodexBarCLI" 2>/dev/null | od -An -tx1 | tr -d ' \n') != 7f454c46 ]]; then
    echo "codexbar: $lib/CodexBarCLI is not the upstream binary; reinstall the CLI tarball first" >&2
    return 1
  fi
  rm -f "$lib/CodexBarCLI.bin" "$lib/codexbar-upstream.real"  # stale launcher state from earlier attempts
  missing=$(codexbar_cli_missing_libs "$lib")
  if [[ -z $missing && ${CODEXBAR_FORCE_LIBXML2_COMPAT:-0} != 1 ]]; then
    rm -rf "$lib/compat"
    return 0
  fi
  if [[ -n $missing && $missing != libxml2.so.2 ]]; then
    echo "codexbar: the upstream CLI cannot load: $(tr '\n' ' ' <<<"$missing")" >&2
    return 1
  fi
  if [[ ! -f "$lib/compat/libxml2.so.2" || $(cat "$stamp" 2>/dev/null) != "$CODEXBAR_LIBXML2_COMMIT" ]]; then
    local tool
    for tool in git meson ninja cc; do
      command -v "$tool" >/dev/null || { echo "codexbar: building libxml2.so.2 needs $tool" >&2; return 1; }
    done
    work=$(mktemp -d)
    echo "Building private libxml2 $CODEXBAR_LIBXML2_TAG for the CodexBar CLI (needs libxml2.so.2)" >&2
    if ! { git -c advice.detachedHead=false clone -q --depth 1 --branch "$CODEXBAR_LIBXML2_TAG" \
             "$CODEXBAR_LIBXML2_REPO" "$work/src" \
         && [[ $(git -C "$work/src" rev-parse HEAD) == "$CODEXBAR_LIBXML2_COMMIT" ]] \
         && meson setup "$work/build" "$work/src" --buildtype=release \
              -Dicu=disabled -Dlzma=disabled -Dzlib=disabled -Dmodules=disabled \
              -Dpython=false -Dreadline=false -Dhistory=false \
              "-Dc_link_args=-Wl,--version-script=$work/src/libxml2.syms" >/dev/null \
         && ninja -C "$work/build" "libxml2.so.${CODEXBAR_LIBXML2_TAG#v}" >/dev/null; }; then
      rm -rf "$work"
      echo "codexbar: could not build libxml2 $CODEXBAR_LIBXML2_TAG (pinned $CODEXBAR_LIBXML2_COMMIT)" >&2
      return 1
    fi
    mkdir -p "$lib/compat.new"
    install -m 0644 "$work/build/libxml2.so.${CODEXBAR_LIBXML2_TAG#v}" "$lib/compat.new/libxml2.so.2"
    install -m 0644 "$work/src/Copyright" "$lib/compat.new/libxml2-Copyright"
    printf '%s\n' "$CODEXBAR_LIBXML2_COMMIT" > "$lib/compat.new/libxml2.commit"
    rm -rf "$work" "$lib/compat"
    mv "$lib/compat.new" "$lib/compat"
  fi
  # Keep the real binary next to its resource bundle and put a launcher in its place.
  # The launcher only ever runs CodexBarCLI.bin, never itself.
  mv -f "$lib/CodexBarCLI" "$lib/CodexBarCLI.bin"
  cat > "$lib/CodexBarCLI.new" <<'EOF'
#!/bin/sh
# Installed by mseries/lib-codexbar.sh: upstream's CLI links libxml2.so.2, which this base no longer
# ships; compat/ holds a private build (see compat/libxml2.commit). Re-run install-codexbar.sh to refresh.
dir=$(CDPATH= cd -- "$(dirname -- "$(readlink -f -- "$0")")" && pwd)
LD_LIBRARY_PATH="$dir/compat${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" exec "$dir/CodexBarCLI.bin" "$@"
EOF
  chmod 0755 "$lib/CodexBarCLI.new"
  mv -f "$lib/CodexBarCLI.new" "$lib/CodexBarCLI"
  missing=$(codexbar_cli_missing_libs "$lib")
  if [[ -n $missing ]]; then
    echo "codexbar: the CLI still cannot load: $(tr '\n' ' ' <<<"$missing")" >&2
    return 1
  fi
}

# codexbar_install_wrapper REPO: replace ~/.local/bin/codexbar atomically so the panel never finds it missing.
codexbar_install_wrapper() {
  local repo=$1
  mkdir -p "$HOME/.local/bin"
  install -m 0755 "$repo/mseries/codexbar-opencode-wrapper.py" "$HOME/.local/bin/codexbar.new"
  mv -f "$HOME/.local/bin/codexbar.new" "$HOME/.local/bin/codexbar"
}
