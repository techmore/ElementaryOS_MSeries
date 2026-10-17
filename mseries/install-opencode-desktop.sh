#!/usr/bin/env bash
# Build and install OpenCode Desktop (arm64) from source; see opencode-desktop/.
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/opencode-desktop/build-opencode-desktop.sh" --install
