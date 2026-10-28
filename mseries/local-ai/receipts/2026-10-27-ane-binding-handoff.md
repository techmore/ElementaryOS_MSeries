# Qwen ANE binding handoff — 2026-10-27

Goal: run the converted Qwen3.8-2B Q4_K_M checkpoint on the M1 Pro Linux ANE, verify its results, then benchmark against equivalent MLX and Rapid-MLX workloads. Prior conversion and the exact checkpoint identity are in `2026-10-27-ane-qwen-conversion.md`. This is unfinished; no Qwen ANE submission or ANE timing has been made.

## New offline findings

`audit-ane-qwen-layout.py` reads the candidate layout plan and the 38 local ANEC headers without opening the device. It found 416 surfaces, no duplicate channels, and six incompatible packed surfaces: `t31` in programs 6, 12, 18, 25, 31 and 37 has shape `[1,1,1,50]`, compiled strides `[128,128,128,2]`, and a 128-byte allocation, while the current staged runner's 64-byte minimum-row packing produces 100 bytes. Runtime packing must use the actual compiled strides rather than infer alignment from logical shape. The plan also has 18 surfaces whose channels are not referenced in its decoded task selectors; those bindings need independent validation rather than being treated as proven. Twenty ANEC headers specify descriptor size `0x300`, while 18 use `0x1f8`. The converter itself documents a 7-bit field warning above `0x1f8`, plus a T6001-specific staged override; safe behavior on this T6000 and this driver is not established. None of these checks proves hardware execution safe.

Reproduce on this laptop:

```sh
python3 mseries/local-ai/audit-ane-qwen-layout.py \
  ~/.cache/mseries-metal2vk/qwen38-ane/mac-receipts/layout-plan-candidate.json \
  ~/.cache/mseries-metal2vk/qwen38-ane/anec-candidate
python3 -m unittest discover -s mseries/local-ai -p test_audit_ane_qwen_layout.py
```

The audit intentionally always reports `submission_allowed: false`: it is not a submission gate or a driver proof. The candidate plan was generated with a local adaptation of upstream `tools/staged-qwen/io_layout.py`, on the mini at `~/Library/Caches/mseries-ane-qwen-20261027/io_layout-candidate.py`. The staged direct runner and patched converter are in `/tmp/mseries-ane-linux-experiments`; persistent patch files are in `mseries/local-ai/patches/`. The candidate ANEC files, layout plan, goldens and manifest are under `~/.cache/mseries-metal2vk/qwen38-ane/`; the matching mini copies are in `~/Library/Caches/mseries-ane-qwen-20261027/`. Temporary paths are not durable; reconstruct from the pinned upstream source and committed patches if missing.

## Memory and next steps

The laptop had about 12.1 GiB `MemAvailable`, below the approximately 13.8 GiB admission estimate (previous 8.38 GB peak plus 6 GiB desktop reserve). Brave, Codex/ChatGPT and Claude account for significant memory; a separate audio model workload was active. No applications or workloads were closed, and cache dropping was not used as a substitute for reclaimable-memory accounting. Identify a safe, user-acceptable idle window or reduce measured model peak without compromising the 6 GiB reserve. Keep the existing worker lock, thermal supervision and no-fallback checks.

Next: implement and unit-test stride-aware packing and unpacking from the compiled layout; compare every planned port and state binding with the HWX/ANEC streams and independently supported T6000 driver behavior; resolve the descriptor-size limit using evidence, not assumptions. Build a guarded first-step replay and compare numerical outputs with the macOS reference (cross-chip byte equality is not assumed). Only then run timed decode with explicit route evidence and matched model, quantization, prompts, warmups and token counts. Existing MLX Qwen3.5 measurements are a different model from this Qwen3.8 checkpoint and must not be presented as a direct speedup comparison. Record memory, temperature, desktop responsiveness and samples in the PR.
