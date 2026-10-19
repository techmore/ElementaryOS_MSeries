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

# codexbar_install_wrapper REPO: replace ~/.local/bin/codexbar atomically so the panel never finds it missing.
codexbar_install_wrapper() {
  local repo=$1
  mkdir -p "$HOME/.local/bin"
  install -m 0755 "$repo/mseries/codexbar-opencode-wrapper.py" "$HOME/.local/bin/codexbar.new"
  mv -f "$HOME/.local/bin/codexbar.new" "$HOME/.local/bin/codexbar"
}
