# Optimization repository

Measured, optional efficiency work lives in
[techmore/ElementaryOS_MSeries_Optimization](https://github.com/techmore/ElementaryOS_MSeries_Optimization)
(public, GPL-3.0, created 2026-10-15; first commit `7d65b03`).

| There | Here |
| --- | --- |
| Power lab (`powerlab/sample.py`: median/p10/p90 battery-power sampler, interrupt rates) | Image wiring, installers, hardware bring-up |
| Efficiency patches and tuning drop-ins, each with measured before/after | Kernel, boot, audio and firmware work (owner-gated, see `AGENTS.md`) |
| Rust ports (`mseries-power` first; the scaffold on `deb/mseries-plugin-repo` moves there with history when its owner agrees) | The packaging and image build that ships the results |
| Goals, method, results log (`docs/EFFICIENCY-GOALS.md`, `RESULTS.md`) | `EFFICIENCY-GOALS.md` here stays as a pointer-level copy |

Rule: a change moves from the optimization repo into the image only with before/after medians from `powerlab`
and an uninstall path. Record the optimization commit in `UPSTREAM-PINS.md` when the image consumes it.
