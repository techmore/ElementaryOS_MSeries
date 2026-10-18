# Unified Aurora 7.2.10 experiment

This lane snapshots draft [upstream PR #139](https://github.com/omacom/linux-aurora/pull/139)
at `582e9ef3d44c93082e8abc740ad3e0a8dde29752`; moving branch tips never update
the build implicitly. `series.json` pins the complete archive hash, source
identity, package identity and host-test entrypoints.

```sh
python3 mseries/aurora/candidate.py prepare --profile unified72 \
  --cache /absolute/work/cache --output /absolute/work/unified72
python3 mseries/aurora/candidate.py check --prepared /absolute/work/unified72
python3 mseries/aurora/candidate.py build --prepared /absolute/work/unified72 \
  --output /absolute/work/unified72-artifacts --jobs 4
```

The build uses the checksum-pinned `.20` full recipe config as a seed, resolves
it against the new source and checks Apple/Rust/16K/USB4/memory support. This is
not the upstream author's Fedora configuration or hardware result. It disables
eGPU drivers and keeps a separate `7.2.10-elementary-aurora72-wip1` module tree
and `linux-image-elementary-aurora72-wip1` Debian package. It creates no boot
entry and changes no default. The fixed `.20` installer/stager cannot deploy it.

The 9 production PMP parser tests and 3 reply-correlation tests pass locally.
Native Image/modules/DTB compilation and package inspection run in the existing
Aurora enhancement workflow, alongside the original `.20` source candidate.
The previously built eGPU profile remains available by manual dispatch.
Full build status is recorded in that run; no local 7.2 hardware boot is claimed.
PMP/PMGR/CPU-idle helpers already present in `.20` are not reapplied as patches.
The M3 camera/thermal/SMC patch series belongs to the separate `.20` enhancement
candidate; it is not silently layered onto the unified upstream snapshot.

Before hardware use, review matching DT/m1n1 and root-unlock/recovery together.
PR #139 is draft, has incomplete gate/soak work, and its contributor M1 Pro
results refer to a J316S and specific earlier tree/config combinations. Shared
display, storage, memory and SEP changes require J314S acceptance. See the
[port plan](../ENERGY-PORT-PLAN-2026-10-18.md) and
[qualification process](../hardware-tests/README.md). The sources retain
upstream licenses and authors; each package includes full corresponding source,
resolved config, build-tool versions and provenance.
