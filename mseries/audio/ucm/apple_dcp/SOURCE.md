`apple_dcp.conf` and `HiFi.conf` are copied unchanged from the unmerged pull request
AsahiLinux/alsa-ucm-conf-asahi#9 ("apple_dcp: add HDMI/DisplayPort output"), head commit
`cb2206/alsa-ucm-conf-asahi@88b52d77b17499bf133316a3642216de518ff254`, fetched 2026-10-18.
License: BSD-3-Clause, the alsa-ucm-conf-asahi repository license
(<https://github.com/AsahiLinux/alsa-ucm-conf-asahi>). Drop these copies once the Asahi package ships them.

They give the kernel's `apple_dcp` sound card (created only with `appledrm.hdmi_audio=1`) a `HiFi` profile and an
`HDMI1` sink. Without them WirePlumber offers only `off` / `pro-audio` for that card.
