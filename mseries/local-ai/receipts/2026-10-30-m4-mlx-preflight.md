# M4 MLX baseline preflight, 2026-10-30

At 2026-10-30 20:09:35 EDT on Apple Mac mini J773g, Gravity Linux kernel `7.1.13-509.gravity.fc44.aarch64+16k`, Mesa package `mesa-vulkan-drivers-26.3.0~devel-103.gravity.fc44.aarch64`, an isolated MLX v0.7.33 GPU smoke failed. The runtime enumerated `Device(gpu, 0)`. The program evaluated `mx.array([1.0]) + 1`, called `mx.eval`, and printed `array([0], dtype=float32)` rather than the expected `[2]`; process exit status was 0. At 20:09:45 EDT the kernel logged `G16: async Work ... timeout without retirement progress`, `firmware retirement failed: ETIMEDOUT`, and `submission pipeline failed: ETIMEDOUT, 1 jobs, 1 issued`. This is a GPU correctness failure and likely device wedge; no further GPU operations were run.

No model weights were downloaded or evaluated after the smoke failed, so there are no M4 model SHA-1s or tokens-per-second measurements. The M1 Pro results are not M4 baselines. No system software, kernel, display configuration or boot state was changed.

- Vendor bundle SHA-256: `bc9f8c7527e1324d25212922ca0afd2acc2411ec7cdd4b26e2773bffdef32f0e`; SHA-1: `7c8b03939ed8448261ea8c04529142a28f9ffefa`.
- MLX wheel `mlx_omarchy-0.32.4.dev202610160529+33630f9c-cp314-cp314-linux_aarch64.whl` SHA-256: `6068ab8370a5e0ffd80778d103114cfb3f42b3153bf4c754465adab036c33d2c`; SHA-1: `7c07b3432c6343321b3537f694fb6a3aa14397b4`.
- [Captured output](2026-10-30-m4-mlx-preflight.log) SHA-256: `559ffaeb36312e86f08a6eb223c5947eabe630633a556a9487872f2afd872e3f`; SHA-1: `35ae6002d35a36ef556eb481e5d20cd9e094a1e8`.
