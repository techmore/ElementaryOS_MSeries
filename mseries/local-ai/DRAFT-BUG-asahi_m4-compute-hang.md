# DRAFT, NOT SENT: asahi_m4 G16 compute submit hangs on first Vulkan compute job (Mac mini M4)

Status: local draft awaiting owner approval. Do not post, file or push without it.
Intended audience (owner to decide): Gravity Linux kernel maintainers; Aurora discussion 130.

## Summary

On an Apple Mac mini (M4, j773g/t8132) running Gravity Linux, a first Vulkan compute dispatch through
Honeykrisp hangs, the `asahi_m4` driver reports a submission timeout, and the render node then fails
every later `DRM_IOCTL_ASAHI_VM_BIND` and submit with EIO until the module is reloaded. Graphics device
enumeration works before the hang.

## Environment

- Mac mini (M4, 2024), `apple,j773g apple,t8132`, 10 GPU cores, 16 GB
- Gravity Linux (Fedora 44 KDE), kernel `7.1.13-509.gravity.fc44.aarch64+16k`, module `asahi_m4`
- Mesa `26.3.0~devel-103.gravity.fc44` (Honeykrisp), Vulkan 1.4.359, device `Apple M4 (G16G B1)`
- Workload: omarchy-mlx v0.7.33 (`33630f9c`), a 1024x1024 float32 matmul via MLX's Vulkan backend

## Observed

```
RuntimeError: [omarchy] Vulkan timeline counter failed to advance for 10000 ms (last observed=0, target=1)
asahi_m4: G16: submission pipeline failed: ETIMEDOUT, 1 jobs, 1 issued
asahi_m4: G16: submission pipeline failed: EIO, 1 jobs, 0 issued   (22 more)
DRM_IOCTL_ASAHI_VM_BIND failed: Input/output error      (fresh vulkaninfo afterwards)
```

Before any compute work: `asahi_m4: UATPageTable::unmap_pages: Page at IOVA 0x2ffff90000 already unmapped`.

## Not yet known (do not claim)

- Whether a trivial non-MLX compute kernel also hangs (reproducer planned: metal2vk `m2v-run.c`
  with a minimal SPIR-V module).
- Which op size or shader feature triggers it.
- Whether the fault is in the kernel driver, Mesa, or MLX's submission pattern.
- Whether the pinned private Honeykrisp build behaves differently.

## Reproducer

TBD after the standalone Vulkan test runs. A minimal one will be attached before this is filed.
