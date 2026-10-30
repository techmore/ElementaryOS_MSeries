# NVIDIA RTX eGPU source kit

This prepares NVIDIA's open GPU kernel modules **595.112.07**, source commit `d8257d95ae5fed364163e4df51db66df8b1ee0d2`, with Joshua Warren's public [16K page-size fix #1480](https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1480) and [ARM64 DMA submap fix #1481](https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1481). Their original patches and SHA-256 pins are retained with authorship; the NVIDIA source includes its own licenses.

```sh
bash mseries/nvidia-egpu/prepare.sh "$HOME/.cache/mseries-nvidia-595-prepared"
```

The preparation checks the exact source commit and patch hashes and applies both changes; it does not build, install, or load modules. Building the NVIDIA module requires a fully prepared, version-matched kernel build tree and matching NVIDIA 595.112.07 userspace. Neither is provided by the current kernel payload package. Do not load a module built against a different kernel. No RTX card is connected here.

The public [Apple tunnel chipset fix #1482](https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1482) targets NVIDIA 615 and does not apply to 595; its original patch is retained as a reference and is **not** applied. The upstream 595 setup used the `RmForceDisableIomapWC=1` registry option as the alternative. No automatic modprobe configuration is installed here. The current downstream combined kernel separately enables Nouveau/NVK; it is not the NVIDIA-open/CUDA path. Firmware `linux-firmware-nvidia-graphics` `20260319.git217ca6e4-0ubuntu1.1` is installed, including GB206 570.144 firmware; this does not install the NVIDIA-open module or CUDA userspace. See the upstream [RTX setup](https://github.com/joshuaswarren/omarchy-egpu/blob/main/cards/rtx-5060-ti/setup.md).
