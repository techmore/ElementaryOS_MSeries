# ANE smoke and mlx-lm patch dry-run — 2026-10-19 (M1 Pro, T6000)

Read-only checks from scratch builds; nothing installed, no driver, kernel or runtime changed.

## omarchy-ane (main 94cceca), host tools built in scratch with `make all`

- `omarchy-ane-check`: SoC node `apple,t6000-ane`; `driver_source=intree` (`ane.ko`, `CONFIG_DRM_ACCEL_ANE=m`); loaded and bound to `285c04000.ane`. **One FAIL**: `/dev/accel/accel0` is `crw-rw---- root:render` (mode 0660). The owner is in `render`, so this is a note for other users, not a blocker; not changed (system setting).
- `omarchy-ane-smoke` (shipped H13 add program, 20 calls): **20/20 bit-exact**, min 0.036 ms, median 0.046 ms, errors 0, golden `5ad7eccd…0dd6`. One boot, one run, an add program only: it shows the in-tree driver executes, not that any model runs on the ANE.

## omarchy-mlx main (61495cb) mlx-lm patches

- Installed mlx-lm is 0.31.3. `mlx-lm-server-skip-logprob-read.patch` exists only in `patches/mlx-lm-0.32/` and targets `mlx_lm/server.py` of the 0.32 API (`StopSequences`). It does not apply to our installed tree (dry-run on a copy: no file to patch). Not a candidate until we move to the 0.32 line.
- `scripts/patch-mlx-lm-rotkv-maskless.py` is likewise 0.32-series only.

## Implication

Nothing from main is portable to the running 0.31.3 stack without a runtime rebuild. The remaining gains need the candidate-build A/B in the bump plan.
