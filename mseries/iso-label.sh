#!/usr/bin/env bash

# Return a portable ISO 9660 volume ID: uppercase ASCII letters, digits, and
# underscores, with the 32-character limit applied after normalization.
iso_volume_label() {
    printf 'ELEMENTARY_%s_%s' "$1" "$2" |
        LC_ALL=C tr '[:lower:]-' '[:upper:]_' |
        LC_ALL=C tr -cd 'A-Z0-9_' |
        cut -c1-32
}
