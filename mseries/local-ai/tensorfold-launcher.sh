#!/usr/bin/env bash
# Select the private Apple GPU compute ICD for this process only.
set -euo pipefail
icd=${MSERIES_HK_ICD:-$HOME/.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json}
[[ -r $icd ]] || { echo "Private Honeykrisp Vulkan ICD not found: $icd" >&2; exit 1; }
export VK_DRIVER_FILES=$icd
exec /usr/libexec/mseries/tensorfold-native-vulkan "$@"
