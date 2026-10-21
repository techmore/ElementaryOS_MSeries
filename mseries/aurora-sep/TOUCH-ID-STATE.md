# Touch ID on this Mac: current state ledger (2026-10-21)

One page of where each layer stands, with the evidence. Update it when something changes; details live in
[XART-GUARD.md](XART-GUARD.md) and [UPSTREAM-MAP.md](UPSTREAM-MAP.md).

## Machine

MacBook Pro 14" (M1 Pro, 2021), `apple,j314s` / `apple,t6000`, `asahi,os-fw-version` 13.5,
`asahi,system-fw-version` 27.0. elementary OS 9. Boot: GRUB default **STABLE .20**; the 7.2 wip2 trial is chosen
per boot. Running when checked: `7.2.10-elementary-aurora72-wip2`, no one-shot armed.

## Layers

| Layer | State | Evidence |
| --- | --- | --- |
| Hardware / device tree | works | local `boot.bin` DTB patch: SEP enabled with alias; `spi@39b108000` + `fingerprint@0` (GPIO 196/195, 8 MHz, mode 2); calibration file present |
| Secure Enclave attach | works | 7 endpoints, `hwrng` registered, `/dev/sep-bio`, `diag/touchid: ready`, `sensor: online` |
| Sensor bring-up | works, intermittent patch ack | stage 0 passes every boot (identifier ~19 ms, session commit ~33 ms); later power-ups sometimes log `sensor patch: no acknowledgment after 250 polls`; enrolment has no retry (verify/attach do) |
| Enrolment in the enclave | works | attempt 3: user catacomb state 7; survives reboot (`identity count 1`, `enrolment survived reboot`) |
| Host save and matching | **blocked** | xART guard level 1 refuses a kind-4 rewrite; fprintd status 0x6; `diag/matching: blocked`; Linux list `aurora-sep-xart-owned.bin` is 0 bytes |
| fprintd / libfprint | running, no prints | `fprintd-list`: no fingers enrolled |
| PAM (sudo, polkit, lock screen) | untouched | `pam_fprintd` in neither `/etc/pam.d/sudo` nor polkit; lock-screen PAM service still unidentified |
| Settings page | merged and installed | PR #392, #411, #412; redesign branch not merged |
| Upstream reporting | nothing posted | wrong-thread comment deleted at owner's request; per-Mac report draft pending owner approval |

## Decisions and risks

- **Owner decision:** run with `options apple_sep xart_guard=0` (what upstream's M1 Pro and SiliconForest do) or keep the
  guard on. Guard off may rewrite shared pre-Linux xART records; macOS Touch ID is then unverified. Upstream also warns
  xART mistakes can force a DFU restore. Guard unchanged.
- **Leftover state:** one identity sits in the enclave, with catacomb files in `/var/lib`, that fprintd cannot use.
- **Temporary change to remove after diagnosis:** `/etc/modprobe.d/mseries-sep-trace.conf` (`sensor_trace=1`).

## Next actions

1. Owner decides on the guard. 2. Redraft the per-Mac report around the new data (guard behaviour on a guarded cold-boot
M1 Pro; enrolment lacks the sensor retry), owner approves, post to `omacom/linux-aurora`. 3. If the guard is turned off:
reboot, enrol once, verify, then wire PAM for sudo and polkit only, password kept as fallback. 4. `wip3` kernel candidate
(PR #413) is a display/base test and does not change any of this.
