# Diskless QEMU callback-module lifetime fixture

This GPL fixture exercises the shared C scheduler with a real loadable backend
module, not an M4 GPU or Rust driver. A dependency-blocked job survives forced
entity fini and scheduler fini. Its module cannot unload while deferred cleanup
owns callback code; after signalling the dependency, cleanup returns the last
reference and unload succeeds. A missing-owner negative detects refcount zero
and powers off before attempting any unsafe unload.

The positive and negative run on the same generic ARM64 kernel, static BusyBox
and init script, with two TCG vCPUs, no network and no host disk devices. Native
MODULE_UNLOAD is enabled only in this isolated test profile; no host module is
loaded. Rust is disabled here; DRM_LIMA selects the common scheduler without
matching a physical GPU. The separate twelve-case Rust/KUnit suite and actual
M4/legacy object compiles cover different parts of the combined recipe.

Prepare current sources with prepare-scheduler-kunit.py. In that kernel source,
use the ARM64 KUnit runner's build subcommand with this directory's kunit.config,
a new build directory, native ARM64 clang21/GNU ld and two jobs:

```sh
python3 tools/testing/kunit/kunit.py build --arch=arm64 --cross_compile= \
  --build_dir=/path/to/module-enabled-build \
  --kunitconfig=/path/to/repo/mseries/m4-mini/testing/module-lifetime/kunit.config \
  --make_options=CC=clang --make_options=LD=ld --make_options=HOSTCC=clang --jobs=2
```

The test runs
with kunit.enable=0 and uses its own tiny initramfs. Then invoke:

```sh
python3 mseries/m4-mini/test-module-lifetime.py \
  --source /path/to/prepared/linux-4fc326f6c25ccceb7515e2635c22e01fde5d3bac \
  --kernel-build /path/to/module-enabled-build --busybox /path/to/static-arm64-busybox \
  --output /path/to/new-positive
```

Use a separate new output and --negative-owner for the negative. The runner
builds only a fixture module, generates a synthetic initramfs and invokes QEMU;
it never invokes a host module loader. Paths must not contain whitespace because
the kernel initramfs-list format does not quote source paths.

The result does not qualify M4 Execution work, firmware shutdown, Rust DRM
file/DMA-buffer unload or native device removal. In particular, M4's completed
job fence must not be mistaken for a joined worker callback. Those ownership
boundaries need separate review. Fixture C is GPL-2.0-only; harness/init recipes
are GPL-3.0-or-later. BusyBox is supplied locally, not redistributed here.
