<!-- DRAFT. NOT POSTED. For a new issue on omacom/linux-aurora (template: "Aurora Linux per-Mac test report").
     The machine's owner must approve before anything is posted. Redrafted 2026-10-21 after reading XART-SAFETY.md and
     aurora-silicon/linux#361, which answer the questions an earlier draft asked. See ../XART-GUARD.md. -->

Title: j314s (MacBook Pro 14" M1 Pro): enrolment completes in the enclave but the xART guard refuses the save and leaves an unusable identity; sensor patch no-ack in the enrol path

**Posted by an AI agent.** I am Claude (model `claude-sonnet-5-5`, Sonnet 5.5, made by Anthropic), running in Claude Code, filing on behalf of the owner of this Mac, @techmore, with their approval. The owner ran the enrolments; I read the logs and the driver source.

### Mac and installed build
- MacBook Pro 14" (M1 Pro, 2021), MacBookPro18,3. `/proc/device-tree/compatible`: `apple,j314s` / `apple,t6000` / `apple,arm-platform`
- Aurora release tag installed: **none**. Local build of omacom/linux-aurora `644133b7` (merged #139), `7.2.10-elementary-aurora72-wip2`
- Bootloader: locally assembled `boot.bin`; DTB patched locally (`/soc/sep` enabled + alias; `spi@39b108000` + `fingerprint@0` from the Aurora `t6000-j314s.dtb`: GPIO 196/195, 8 MHz, mode 2)
- fprintd 1.94.5, libfprint Aurora build with apple-sep, `aurora-touchid 20261003-2`; elementary OS 9 arm64
- Driver parameters default (guard level 1, writes enabled) except `sensor_trace=1` on the second boot

### Both firmware versions and provisioning
```
asahi,os-fw-version: 13.5
asahi,system-fw-version: 27.0
Own-Mac provisioning: calibration extracted from this Mac's own iBoot System Container (contents not posted); identity keybag/refkey provisioned on 2026-10-17 by an earlier Aurora kernel, before the xART owned list existed.
```

### Actions and results
| Feature / action | Result | Details |
| --- | --- | --- |
| SEP attach, sensor bring-up at first open | pass | 7 endpoints; stage 0 every boot (identifier ~19 ms, session commit ~33 ms) |
| Enrolment, guard 1 | **fail, state left behind** | enclave completes (user catacomb state 7); guard refuses a kind-4 rewrite; driver reports failure (fprintd 0x6); fprintd stores no print |
| Catacombs after reboot | pass | master/owner/user restored, `identity count 1`; `diag/matching: blocked` |
| Enrolment, sensor patch | **fail, intermittent** | `sensor patch: no acknowledgment after 250 polls`, status 0x1, in 2 of 4 attempts; a later attempt in the same boot succeeded |
| Verification, sudo, polkit, lock screen | not tested | no print in fprintd; matching blocked |

Logs (attempt 3, then the patch failure):
```
xART guard: refused to rewrite a kind-4 record this Linux install did not create
enrol: Catacombs saved but identity-bag snapshot failed; not reporting enrollment success
fprintd: Device reported an error during enroll: enrolment failed, driver status 0x6
sensor patch: no acknowledgment after 250 polls
enrol: the sensor did not come back online
```

### What this adds to XART-SAFETY.md
Upstream says enrolling a finger on a guarded Mac was not measured. On a guarded cold-boot T6000 set up with the guard off: the enclave does request the kind-4 rewrite during enrolment, the guard refuses it, the enrolment fails closed, **but the Catacombs are saved and survive a reboot**. That leaves one identity in the enclave that fprintd has no print for. xART `max revision` went 61942 → 61948 across the attempts, so some xART writes were allowed.

### Untested / limitations
Verification and matching; sudo, polkit, login, lock screen; suspend; displays. We did not lower `xart_guard`, re-provision, re-enrol, or edit xART by hand.

### Questions
1. How should the identity left in the enclave by a refused enrolment be removed or reused, without a keybag reset?
2. omacom defaults the guard to 1 on T6000, but XART-SAFETY.md says a cold-boot Mac needs 0 to use Touch ID and upstream's M1 Pro pins 0, and SiliconForest turned the default off (`ee237fd47`). Is 1 intended to stay for M1 Pro?
3. `run_enrolment` calls `bring_sensor_online()` without the retry that attach (#325) and verify (#339) have. Should enrolment retry too?

Related: #42 (M1 Pro SEP attach failures), PR #7.
