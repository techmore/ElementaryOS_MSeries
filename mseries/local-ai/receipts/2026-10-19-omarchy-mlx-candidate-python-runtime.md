# omarchy-mlx candidate Python runtime — 2026-10-19 (M1 Pro, G13S C0)

Candidate source: `61495cb66cb9a5fb8e127001c7c1eb959a9d6c22` (public main). Installed v0.7.33 was untouched. Build and venv are under `~/.cache/omarchy-mlx-candidate-61495cb` and `~/.cache/omarchy-mlx-wheel-candidate-61495cb`; no system runtime or package was installed.

## Build

- Build source archive: MLX commit `9c3d35571ac450a8ecf5c17b4d0e3fac52c08bc8`, archive SHA-256 `3e564bf7a0d5e5bac3a56fc26668cdcedd4a9db9fbfbf2bb6d762632ceb6f65a`.
- `omarchy-mlx/mlx.lock` says version 0.32.3, but this checksum-verified archive has `mlx/version.h` values 0.32.4. The produced wheel metadata is `0.32.4.dev202610191211+61495cb`; investigate this upstream lock/version mismatch before a runtime bump.
- Host did not have `lapacke.h` or Python 3.14 C headers. Python development packages `python3.14-dev` and `libpython3.14-dev` version `3.14.4-1ubuntu0.2` were downloaded and unpacked under the candidate cache only. No apt install or system file change.
- Built with `MLX_BUILD_CPU=OFF`, `MLX_BUILD_OMARCHY=ON`, `MLX_BUILD_PYTHON_BINDINGS=ON`, `MLX_OMARCHY_ANE_DEVICE=ON`, two build jobs, low priority. The build helper in the cached source clone was locally adjusted to skip its CPU/LAPACKE guard and point CMake at the cached Python headers. Do not treat this as the upstream default release build.
- The 458 MB pinned encoder bundle staged from the installed private runtime and passed `verify_runtime_assets.py`. `stamp_worker_pin.py` stamped the wheel; `openblas_isolation.py check` passed (the CPU-off library has no bare OpenBLAS dependency).

## Artifact and smoke

- Wheel: `mlx_omarchy-0.32.4.dev202610191211+61495cb-cp314-cp314-linux_aarch64.whl`
- SHA-256 after worker-pin stamping: `cf7cfab014b067dd0d43328f0630294e176d32ac70cf99233f580a1905f528d5`.
- Installed with `pip --no-deps` into the separate candidate venv. The candidate `mlx.core` resolves from that venv; mlx-lm 0.31.3 and its Python dependencies resolve through a read-only path entry to the existing runtime's site-packages.
- With `OMARCHY_MLX_SYSTEM_PREFIX` and `VK_DRIVER_FILES` pointed at the existing private runtime, `mx.set_default_device(mx.gpu); mx.array([1,2,3]).sum().item()` returned 6. This is a tiny GPU smoke, not a model result or model qualification. Mesa emitted its existing 26.0.8 warning; no Mesa was changed.

## Model readiness

The everyday service was failed because the pinned 4B weights were missing. A direct `snapshot_download` of `mlx-community/Qwen3.5-4B-MLX-4bit` revision `32f3e8ecf65426fc3306969496342d504bfa13f3` is in progress in `~/.cache/huggingface/hub`, unauthenticated and low priority. At the last observation it was still downloading; verify `config.json` and `model.safetensors` against `qwen35-4b-catalog-entry.json` when complete. No model generation ran and no services were started or stopped.
