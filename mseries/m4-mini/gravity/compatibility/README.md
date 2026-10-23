# Elementary M4 compatibility backports

These public-source adaptations are separate from the unchanged Gravity ARM64
packaging exports. R5 is the last completed kernel package. R6 compiled and
passed independent package checks, but its M4 WFI selector runs at
`early_initcall`, after the boot CPU can already idle. R6 is therefore historical
and superseded.

The current source recipe targets R7. It keeps the R6 WFI/WFxT, built-in
ISO9660/SCSI CD-ROM, Apple watchdog and scheduler fixes, then adds Aurora's
boot-CPU-before-first-idle WFI initialization and two BCM4388 Bluetooth fixes.
The R7 kernel build and package inspection are pending. The M4 mini is not
available for native tests.

| Patch | Purpose / upstream |
| --- | --- |
| 0001 | Initialize scheduler storage; Aurora 6c2d17f / 0d1871c |
| 0002 | Retain terminal-timeout M4 jobs; Aurora 0f89327 |
| 0003 | Separate finalization owner from job-held allocation; Aurora 7ba04b6 |
| 0004 | Pin callback modules, propagate DRM fops owner, permanently drain work; Aurora c163a8d |
| 0005 | Independent timeout state and field-only callback borrows; Aurora 0f89327 |
| 0006 | Parent-synchronized cancellation, exact accounting and paired stop removal; Aurora c9be905 / d1ebc54, current ed55042 callback |
| 0007 | M4+ register-preserving WFI and forced WFxT-off override; Aurora c407e1097ba74b464982c66483ba507a50ed927a / 3f0822d73dbe341d8073a9db05b316cb564dc92f |
| 0008 | Select register-preserving WFI from `smp_prepare_boot_cpu()` before first idle; Aurora 34649b455f4a |
| 0009 | Preserve BCM4388 common calibration-property setup; Aurora f7c762f2ef6b5d6a04394e433e1aa56dbb50ec4a |
| 0010 | Defer BCM4388 Bluetooth until its Wi-Fi function binds; Aurora 053566b82614496ae4b99017680f113376b3ba24 |

The T8132 split-channel ADMAC change from Aurora is already present in the
pinned Gravity driver and enabled by the J773g DT, so it is not duplicated here.
Other reviewed Aurora changes to T6040/T6041 M4 Pro/Max or G17-specific code are
outside this plain-M4 candidate. The DART output-range hardening remains a
reviewed follow-up; the candidate has not been tested with malformed or
boundary-crossing mappings.

`package-versions.json` binds R3, R4, R5, R6 and R7 to distinct immutable patch
sets; `resulting-files-by-version.json` preserves the matching source hashes.
R7 source checks require the Apple selector call inside `smp_prepare_boot_cpu()`
before the boot CPU idle path, verify the linked selector symbol, and check that
BCM4388 Bluetooth defers until Wi-Fi binds. These are build/source gates, not
native hardware qualification.
