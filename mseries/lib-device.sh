# Per-model hardware profile, read from the device tree. Sourced by
# transform/elementary-grow.sh and mseries/enhance.sh callers; defines functions only.
#
# Matching is whole-string and case-folded against the NUL-separated
# compatible entries, after omarchy's omarchy-hw-match-device-tree (MIT,
# omacom/omarchy). ELEMENTARY_DT_COMPATIBLE points tests at a fixture.
#
# Desktop boards come from aurora-silicon.github.io's device list (every
# Mac mini, Mac Studio, Mac Pro and iMac model): they have no battery, lid,
# notch or built-in keyboard backlight, so those pieces are not installed.

MSERIES_DESKTOP_BOARDS="apple,j180d apple,j274 apple,j375c apple,j375d apple,j433 apple,j434 apple,j456 apple,j457 apple,j473 apple,j474s apple,j475c apple,j475d apple,j575c apple,j575d apple,j623 apple,j624 apple,j773g apple,j773s apple,j775c apple,j775d apple,j873g apple,j873s"

mseries_dt_boards() {
  local entry
  [[ -r ${ELEMENTARY_DT_COMPATIBLE:-/proc/device-tree/compatible} ]] || return 0
  while IFS= read -r -d '' entry; do
    printf '%s\n' "$entry" | tr '[:upper:]' '[:lower:]'
  done <"${ELEMENTARY_DT_COMPATIBLE:-/proc/device-tree/compatible}"
}

# Prints "desktop", "laptop" or "unknown" (no Apple board in the device tree).
mseries_device_class() {
  local entry board seen=0
  while IFS= read -r entry; do
    [[ $entry == apple,j* ]] || continue
    seen=1
    for board in $MSERIES_DESKTOP_BOARDS; do
      [[ $entry == "$board" ]] && { echo desktop; return 0; }
    done
  done < <(mseries_dt_boards)
  if ((seen)); then echo laptop; else echo unknown; fi
}
