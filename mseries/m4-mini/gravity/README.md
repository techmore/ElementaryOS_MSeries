# Gravity configuration provenance

The two config overlays are retained unchanged from GravityLinux/packages at
711c2a110416d28010ccdd118b83111776bff207, kernel/gravity.config and
kernel/gravity-aarch64.config. They augment the Asahi 16 KiB configuration.
https://github.com/GravityLinux/packages/tree/711c2a110416d28010ccdd118b83111776bff207/kernel

DRM_ASAHI_M4 is a separate driver and must be enabled explicitly. These reference
overlays include Gravity's protected J773g speaker implementation. This is a
source-build configuration, not confirmation of speaker safety on this owner’s
machine. Package release provenance and firmware remain separate requirements.
