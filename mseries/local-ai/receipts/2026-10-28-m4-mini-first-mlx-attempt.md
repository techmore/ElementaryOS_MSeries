# M4 Mac mini first MLX attempt: GPU detected, first compute job hangs, 2026-10-28

Result: **FAIL, not qualified.** MLX enumerates the M4 GPU, but the first compute job never
completes and the kernel GPU driver then wedges until reloaded. No model was run and no
performance number exists. This receipt records the negative result and its evidence.

## Host

- Apple Mac mini (M4, 2024), `apple,j773g apple,t8132`, 10 GPU cores, 16 GB RAM.
- Gravity Linux (Fedora 44, KDE), kernel `7.1.13-509.gravity.fc44.aarch64+16k`,
  GPU module `asahi_m4` (in-tree).
- Mesa `26.3.0~devel-103.gravity.fc44` (system, Honeykrisp). `vulkaninfo`: `Apple M4 (G16G B1)`,
  API 1.4.359, `DRIVER_ID_MESA_HONEYKRISP`, ICD `/usr/share/vulkan/icd.d/asahi_icd.aarch64.json`.
- Python 3.14.8.

## Install (worked)

omarchy-mlx `33630f9c1eeefe5fc985a28bed0585432c2c014e` (v0.7.33) with vendor wheels
`omarchy-mlx-vendor-wheels-v0.7.33-cp314-aarch64.tar`, sha256
`bc9f8c7527e1324d25212922ca0afd2acc2411ec7cdd4b26e2773bffdef32f0e` (verified). Staged with
`install.sh --system --dest-root <dir> --vendor ... --lock ... --python /usr/bin/python3.14`
(offline, hash-locked, no root, no pacman). All mlx-lm serve patches applied. The system Mesa was
used; the private `joshuaswarren/mesa-1` compute driver was **not** built.

## Run

`mx.default_device()` returned `Device(gpu, 0)`; `mx.device_info()` reported `Apple M4 (G16G B1)`,
driver Honeykrisp, `unified_memory: 1`, `max_recommended_working_set_size` 8220835840.

First compute job, `a = mx.random.normal((1024, 1024)); b = a @ a; mx.eval(b)`:

```
RuntimeError: [omarchy] Vulkan timeline counter failed to advance for 10000 ms
(last observed=0, target=1). The device may be hung; no CPU fallback is available.
```

Kernel log at the same time (`journalctl -k`, 2026-10-28 21:07:59):

```
asahi_m4: G16: submission pipeline failed: ETIMEDOUT, 1 jobs, 1 issued
asahi_m4: G16: submission pipeline failed: EIO, 1 jobs, 0 issued   (22 more, EIO)
```

Earlier, at 21:03:12 and before any MLX run: `asahi_m4: UATPageTable::unmap_pages: Page at IOVA
0x2ffff90000 already unmapped` (twice).

After the hang, a fresh `vulkaninfo` fails with `DRM_IOCTL_ASAHI_VM_BIND failed: Input/output
error` and `BO creation failed`, and only llvmpipe enumerates. A fresh MLX process reports
`no Vulkan physical devices found`. The display keeps working (it uses the DCP driver).

## Not yet done

- The smaller-op bisect (tiny add, 1M elementwise, matmul 64/256/1024 f16) did not run: the GPU was
  already wedged and a reload needs root.
- The pinned private Honeykrisp (`mesa-1` `7faf04c065`, as in `build-local-ai`) was not tried.
- Not yet known whether the fault is in `asahi_m4`, Mesa, or MLX's Vulkan submission pattern.

## Next

1. Reload `asahi_m4` (or reboot), rerun the bisect one process per case.
2. Build the pinned compute driver and compare against system Mesa.
3. Standalone Vulkan compute reproducer, to separate driver bugs from MLX.
