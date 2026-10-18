# Realtime English evidence, M1 Pro 32 GB — October18

English speech → English text only. Public-file trials, no new microphone/owner
window. [Interpretation and limits](../../../dictation/REALTIME-ENGLISH.md).

Each cohort retains its original receipts/attempts, policy and source hashes.
`source-blobs/<sha256>.py` deduplicates exact evaluated public code; `snapshots.json`
maps each cohort-relative filename to a blob. Reconstruct the evaluated-source
layout from that mapping before running a harness. Blobs are bytes, not rewritten
current source. `english-ui-regression-v2.json` pins the later coalescing fix; it
does not replace the English panel's real-model trial. Individual final transcripts
and provisional events remain present, including Moonshine errors.

`driver-snapshots/` preserves the exact queue/admission/resource samplers. These
expect the original sibling workspace layout and matching reconstructed source;
they are historical evidence, not an instruction to replay completed trials.

`pins/` records model revisions/actual digests, public clip IDs and derived PCM
digests. Weights/audio are not included. LibriSpeech CC-BY4.0: Vassil Panayotov,
Guoguo Chen, Daniel Povey and Sanjeev Khudanpur, https://www.openslr.org/12 .
Principal clip:1089-134686-0000, duration10.435s, PCM SHA
33c6c68d943a22d5272bf8d5e1f86af9d89d901fb7da35961a692de7591a534c.
`unsupported-original-gguf/` retains the original format rejection without a
quality score. `source-audit.json` is a point-in-time public upstream audit.

`export-receipts.py` documents the allowlisted export from private queue folders;
it does not read app data. Full logs, settings, credentials, real tasks/journals,
audio and signed URLs are excluded. Home paths in JSON become `<HOME>`. Source
blobs retain portable `Path.home()` expressions; no owner content is embedded.
Checksums cover each public artifact except the checksum file itself.
