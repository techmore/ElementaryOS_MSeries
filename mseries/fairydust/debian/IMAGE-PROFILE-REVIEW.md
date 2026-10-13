# Image Profile Review — fairydust (static only, no builds)

Scope: `.github/workflows/daily-9.0.yml`, `mkosi.images/base/mkosi.profiles/fairydust/mkosi.conf`, `mkosi.images/liveiso/mkosi.profiles/fairydust/mkosi.conf`, `mseries/fairydust/debian/fetch-asahi-boot-packages.sh`. No private files/logs inspected; no builds, installs, network verification, or agents.

## 1. Workflow (`daily-9.0.yml`) — pass with notes

- Expression/dependency logic is correct:
  - `build-kernel` gated on `if: inputs.fairydust` (boolean dispatch input) — skipped cleanly on default builds.
  - `build` uses `needs: build-kernel` + `if: always() && (!inputs.fairydust || needs.build-kernel.result == 'success')`. Default (`false`) still runs; `true` runs only on kernel-job success; `true` + kernel failure correctly skips. No gating mistake.
  - String interpolation `[[ "${{ inputs.fairydust }}" == "true" ]]` (line 95) is consistent with the boolean `if:` elsewhere; not a bug.
- Download/verify steps (lines 76–83) are correctly gated on `inputs.fairydust`, so the default path never touches `mkosi.packages/`.
- Default path unchanged: `else → just do-daily` (line 102); fairydust path uses `--profile=daily,fairydust` (line 96). Provenance/status steps (lines 84–89) only add `build-record/` files.
- Minor observations (not blockers):
  - `SHA256SUMS` provenance is self-consistent, not independently pinned: it is generated in the same job (`sha256sum *.deb > SHA256SUMS`, line 48) and re-checked later. Independent pinning rests on the kernel tarball SHA (line 41) and `UPSTREAM-SHA256SUMS`. Worth stating in the file header so readers don't over-interpret the `SHA256SUMS` check.
  - Artifact round-trip uses `fairydust-kernel-packages-${{ github.run_id }}` for both upload and download in the same run — correct.

## 2. Base profile (`base/.../fairydust/mkosi.conf`) — pass

- No `PackageDirectory=`/`Repository=` override; relies on repo-root `mkosi.packages/` populated by the workflow (lines 45–47). Consistent with the header comment. No local-repo mistake visible in this file.
- Version pins match the other two files exactly:
  - `linux-image-7.1.13-elementary-fairydust-usb4=7.1.13+elementary.usb4.3` vs workflow line 46 `..._7.1.13+elementary.usb4.3_arm64.deb` — match.
  - `m1n1=1.5.2-2ubuntu0.1~asahi1` vs fetch line 18 filename — match.
  - `u-boot-asahi=2025.10-2-1` vs fetch line 20 filename — match.
- `[Match] Architecture=arm64` correctly scopes the profile; default (non-fairydust / non-arm64) builds are unaffected since the profile is only loaded via `--profile=daily,fairydust`.

## 3. LiveISO profile (`liveiso/.../fairydust/mkosi.conf`)

- Intent (keep ordinary initrd modules, add Apple input modules early) is clear and additive-only.
- Confirmed from repository precedent: the same `default` token appears in the existing liveiso and sysupdate `KernelInitrdModules=` configs, and the immediately preceding OS 9 CI build parsed all mkosi configs successfully. Keep it for consistency. The new `hid_apple` and `hid_magicmouse` entries follow the existing sysupdate ARM64 profile.

## 4. Fetch script (`fetch-asahi-boot-packages.sh`) — pass

- Correct: `set -euo pipefail`, HTTPS-only curl (`--proto '=https' --tlsv1.2`, `--fail`, retries), per-file SHA-256 check with delete-on-mismatch, and `UPSTREAM-SHA256SUMS` written as `sha + basename`, which matches the workflow's `(cd mkosi.packages && sha256sum --check UPSTREAM-SHA256SUMS)` usage.
- SHAs and filenames are well-formed (64-hex; versions match base profile per §2). Live correctness against the PPA was not verified (no network per task constraints).
- Nit: `UPSTREAM-SHA256SUMS` is appended (`>>`, line 16) while `SHA256SUMS` is truncated (`>`, workflow line 48). Re-running the fetch into a non-empty dir duplicates entries (harmless for `sha256sum --check`, but noisy). Consider `: > "$out/UPSTREAM-SHA256SUMS"` after `mkdir -p` if idempotent reruns matter.

## 5. Default builds stay unchanged — yes

- Workflow default path skips kernel build/download/verify and runs unmodified `just do-daily` without the fairydust profile.
- Both mkosi profiles are opt-in (`--profile=...,fairydust` + `Architecture=arm64` match).
- Fetch script is standalone and only invoked on the fairydust path.

## Verdict

No expression, dependency, version-string, or local-package wiring errors found. Repository CI precedent confirms the `default` module token. The fetch helper now truncates its manifest for clean reruns.
