# Draft issue for joshuaswarren/mesa-1 — not posted

**Title:** agx: `pick_regs` segfault in `agx_ra` for the software f16 16x16x16 cooperative-matrix shader since "skip the register-pressure scheduler for compute shaders"

**Where:** `honeykrisp-omarchy-v3` tip `f144c7949b` (also `ff013781c00` and later on that branch). Hardware: MacBookPro18,3, M1 Pro (G13S C0), Mesa `26.3.0-devel`, release build (`-Dbuildtype=release`, same flags as `mseries/local-ai/install.sh`).

**Repro** (`tests/cmshape2.c`, build per its header):

```
VK_DRIVER_FILES=<icd.json> AGX_SIMDMAT=1 MESA_SHADER_CACHE_DISABLE=true \
  ./cmshape2 16 16 16 f16 f16 f16 f16 row randint 7 16
```

Segfault (exit 139) while creating the compute pipeline. The same shape passes at workgroup size 32 (hardware path). Workgroup sizes 1, 8, 16, 33 and 48 (all software-lowering cases in `run_matrix2.sh`'s "workgroup sizes" section, f16 rows) crash; the f32 8x8x8 rows in that section pass.

Backtrace (release build, no symbols beyond exports):

```
#0 pick_regs
#1 agx_ra
#2 agx_compile_shader_nir
#3 hk_compile_nir
#4 hk_compile_shader / hk_compile_shaders
#5 vk_compile_shaders
#6 vk_common_CreateComputePipelines
```

**Bisect** (linear stack, good `f06b1b24b67`, bad `f144c7949b`, 5 builds, script and trace in this directory): first bad commit `ff013781c00` "agx: skip the register-pressure scheduler for compute shaders". Its parent-side neighbour `50cf0599131` passes.

**Confirmed workaround:** on the tip, `AGX_SCHED_COMPUTE=1` (restores `agx_pressure_schedule` for compute) makes the case pass with 0 mismatches. Without it, the case crashes.

**Reading (hypothesis, not verified):** with the scheduler skipped, the large software-lowered f16 cooperative-matrix shader reaches register allocation with much higher pressure and `pick_regs` dereferences or indexes something it should not when it cannot find a free range. I did not build a debug Mesa or read `agx_register_allocate.c`.

**Impact for us:** the private compute ICD is used by MLX. The omarchy-mlx C++ tests (runtime, reduce-row, vocab-tail, gdn-gqa, matmul-family) pass identically on the pin and on this tip, so the reachable MLX kernels do not appear to hit this shader, but any compute shader that gets large enough could. The pin `7faf04c065` does not contain `ff013781c00`.

**Ask:** either guard `pick_regs` against the no-free-register case (fail the compile instead of crashing) or keep the scheduler on for shaders above a register-pressure threshold, then add `16 16 16 f16 … row randint 7 16` to `tests/run_matrix2.sh` as a regression.
