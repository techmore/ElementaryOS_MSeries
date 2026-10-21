# Upstream contribution review — October 21, 2026

## Scope and canonical repositories

Current development is [omacom/linux-aurora](https://github.com/omacom/linux-aurora).
The personal [iconidentify/aurora-linux](https://github.com/iconidentify/aurora-linux)
repository is archived and explicitly points development there. `aurora-wip` is
a branch, not a separate current `iconidentify/aurora-wip` repository.
Reviewed immutable refs: integration/aurora `faed71028380b969ed9c943e3ab41d99ca3b9c1a`,
aurora-wip `4ec597a7427da2cf03c899406b7997c875d4a9fb`.
[Machine receipt](upstream-review-2026-10-21.json).

## No new dock kernel patch to submit

The tested wip2 Image is Aurora's already-merged 7.2 source with our resolved
recipe config and no active local kernel patch. Actual three-port picture is
useful J314S qualification evidence, not a newly authored driver fix. Preserve
that attribution. The boot shared legacy DT strategy and Debian package/Arch
unlock/GRUB receipt tooling are distribution integration, not automatically a
Linux kernel patch. A hardware report could be useful after review; none sent.

## Concrete candidate: stale DART host fixture

Current integration's [host harness](https://github.com/omacom/linux-aurora/blob/faed71028380b969ed9c943e3ab41d99ca3b9c1a/tools/asahi/apple-dart-range-tests.py)
and [production driver](https://github.com/omacom/linux-aurora/blob/faed71028380b969ed9c943e3ab41d99ca3b9c1a/drivers/iommu/apple-dart.c)
are byte-identical to our earlier pinned exercised files. The fixture is stale
against the current driver API: missing type/firmware flags, sync signature and
drain-on-error expectation. Retained [host-only patch](boot-preflight-2026-10-21/dart-range-host-fixture.patch)
adapts it and adds firmware mirror/handoff and two-stream error controls.
Production driver unchanged. `git apply --check` passes on current immutable
integration; existing 12 passing controls can be reused because both source
hashes match. Original failed compilation is retained.

An older `fix/migration-test-fixtures` branch contains partial adaptation, but
that head belongs to merged [PR #64](https://github.com/omacom/linux-aurora/pull/64)
from October 11, not an equivalent current fix: it has `fw_mirror` and the
three-argument sync but lacks later `u32`/`fw_handoff` and error-drain changes.
The reviewed aurora-wip ref lacks this harness path. Scoped PR searches for
DART/range-tests/flush did not reveal the same proposal; this is not exhaustive
proof about every contributor branch.

**Recommendation:** prepare a small host-fixture patch against integration,
reuse precise source-bound controls and retain licensing/author attribution.
Do not claim a runtime DART/dock fix. No upstream PR, issue or comment was sent.

## Possible later userspace diagnostic

`mseries/hardware/dock-port-timing.py` and its 5 state-machine tests provide
read-only per-port partner/dock/DRM/compositor timing. It currently depends on
our hardware receipt and Mutter DisplayConfig and measures detected state,
not visible pixels. Generic packaging/decoupling, repeated trials and stable
stage definitions are needed before proposing it to upstream diagnostic tools.
The live samples and raw executed runner are retained with the hardware report.

Native GTK/Granite focus, Rust Pantheon attention and compositor lifecycle logs
belong to elementaryOS_MSeries, rather than Aurora's kernel tree.
