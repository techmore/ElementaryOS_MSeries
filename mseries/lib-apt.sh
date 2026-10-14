#!/usr/bin/env bash
# Reuse a successful repository refresh only within one installer batch.
mseries_apt_sources_digest() {
  {
    if [[ -f /etc/apt/sources.list ]]; then
      sha256sum /etc/apt/sources.list
    fi
    local directory
    for directory in /etc/apt/sources.list.d /etc/apt/keyrings /usr/share/keyrings; do
      [[ -d $directory ]] || continue
      find -L "$directory" -type f -print0 | sort -z | xargs -0 -r sha256sum
    done
  } | sha256sum | cut -d' ' -f1
}

mseries_apt_refresh() {
  local batch=${MSERIES_APT_BATCH_DIR:-} digest stamp started=$SECONDS
  if [[ -n $batch ]]; then
    digest=$(mseries_apt_sources_digest) || return
    stamp=$batch/refresh.sha256
    if [[ -f $stamp && $(cat "$stamp") == "$digest" ]]; then
      echo 'APT: reusing repository metadata refreshed earlier in this batch.'
      return 0
    fi
  fi
  # APT otherwise permits transient fetch failures with exit 0 and stale lists.
  sudo apt-get update --error-on=any -qq || return
  echo "APT: repository refresh completed in $((SECONDS - started))s."
  if [[ -n $batch && $(mseries_apt_sources_digest) == "$digest" ]]; then
    printf '%s\n' "$digest" >"$stamp.$$"
    mv -f "$stamp.$$" "$stamp"
  fi
}
