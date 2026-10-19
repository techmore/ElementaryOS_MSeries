# J314S candidate boot hang: offline review — 2026-10-18

The owner reports that the attempted candidate boot displayed kernel messages,
hung, and did not complete boot. Treat the trial as failed. Exact failing
instruction/driver is unknown: none of the 49 retained journaled boots identifies
`7.1.12-elementary-aurora20-enh1`, and pstore is empty. Previous `.20` boot ended
at 19:53:40 EDT with DCP endpoint shutdown timeouts; current `.20` boot began at
19:57:03 EDT. Those shutdown messages do not establish the candidate hang cause.

## Offline findings

- Candidate kernel, initramfs and shared boot payload match the staging hashes.
- Early archive and every nonmodule initramfs entry match the working `.20`
  baseline, including encrypted-root setup. All 93 candidate modules match their
  installed candidate bytes; dependency references stay inside the archive.
- Runtime baseline vs frozen candidate config differs in the intended UDMABUF,
  DMABUF_HEAPS and DMABUF_HEAPS_SYSTEM settings, release naming and recorded
  compiler/bindgen/pahole version fields. Both are ARM64 with 16K pages.
- Candidate and working J314S DTB bytes match the retained staging proof.
- Diskless QEMU trials of both images produced no serial evidence. Both configs
  omit the PL011 console required by that virtual machine. This is inconclusive,
  not a candidate boot pass or reproduction of the hardware failure.
- GRUB next_entry is empty; working `.20` remains running. No kernel, boot payload,
  module tree or boot selection was modified during the investigation.

## Repair the evidence gap without another reboot

The installed capture service starts in the logged-in user session and cannot
record a pre-login hang. `prepare-boot-diagnostics.py` now creates a **separate,
private, uninstalled** initramfs with stage-only markers around each initramfs
hook, configured-module loading, root resolution/mount and switch_root. Hook
failure status is preserved. It does not enable shell command tracing or change
unlock commands/modules/firmware. Only `init` and `init_functions` change;
the early archive and all other entries are checked byte-for-byte.

The prepared diagnostic receipt and original archive audit are retained beside
this report. Suggested additional kernel arguments are recorded as separate
JSON tokens, **not an installed GRUB entry**. Kernel `initcall_debug` can identify
the last started initcall if a later explicitly authorized trial reaches it;
initramfs markers cover later userspace. Neither guarantees persistence before
root mount, so the last visible messages still need capture if that trial hangs.
No future trial is armed. Do not promote the failed candidate or claim that this
diagnostic preparation fixes its unknown driver/hardware failure.

Validation: five new tests cover archive preservation, unsupported/repeated
instrumentation refusal, private output guards, hook status preservation and
changed/missing module detection. The real candidate archive passes the audit;
real generated init/init_functions pass shell syntax checks. Existing Aurora
tests are run with this change. No new hardware inference or suspend test.
