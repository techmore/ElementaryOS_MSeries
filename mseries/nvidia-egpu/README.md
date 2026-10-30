# NVIDIA RTX eGPU source kit

This prepares NVIDIA's open GPU kernel modules **595.112.07**, source commit `d8257d95ae5fed364163e4df51db66df8b1ee0d2`, with Joshua Warren's public [16K page-size fix #1480](https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1480), [ARM64 DMA submap fix #1481](https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1481), and [Apple tunnel chipset fix #1482](https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1482). Their original patches and SHA-256 pins are retained with authorship; the NVIDIA source includes its own licenses.

```sh
bash mseries/nvidia-egpu/prepare.sh "$HOME/.cache/mseries-nvidia-595-prepared"
```

The preparation checks the exact source commit and patch hashes and applies all three changes; it does not build, install, or load modules. Building the NVIDIA module requires a fully prepared, version-matched kernel build tree and matching NVIDIA 595.112.07 userspace. Neither is provided by the current kernel payload package. Do not load a module built against a different kernel. No RTX card is connected here.

The original #1482 patch targets NVIDIA 615 and is retained unchanged as a reference. Its 595 rebase keeps all 29 added lines byte-identical, retains the older tree's reserved chipset value, and omits unrelated TB500 context. The 595 source kit applies that rebase after the two 16K fixes. The upstream 595 setup also describes `RmForceDisableIomapWC=1` as an alternative; no automatic modprobe configuration is installed here. The current downstream combined kernel separately enables Nouveau/NVK; it is not the NVIDIA-open/CUDA path. Firmware `linux-firmware-nvidia-graphics` `20260319.git217ca6e4-0ubuntu1.1` is installed, including GB206 570.144 firmware; this does not install the NVIDIA-open module or CUDA userspace. See the upstream [RTX setup](https://github.com/joshuaswarren/omarchy-egpu/blob/main/cards/rtx-5060-ti/setup.md).
