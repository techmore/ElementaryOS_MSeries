# AirDrop radio on the j314s (MacBook Pro 14", M1 Pro): what is validated and what is not

Source compatibility and hardware preflight were checked on 2026-10-18. On
2026-10-18 the owner then ran radio setup and a two-minute visibility window;
on 2026-10-22 the idle setup service was enabled again after a reboot had removed
the interface. Real file transfer acceptance remains open.

## Validated (by reading and diffing code, and by read-only checks)

| Question | Evidence |
|---|---|
| Is this the same Wi-Fi chip upstream verified? | `lspci`: BCM4387 `14e4:4433`. omdrop-awdl's "Known to work" table lists the MacBook Pro 16" (2021), M1 Pro, BCM4387: "Sending and receiving, iPhone and Mac, Everyone and Contacts Only". The 14" M1 Pro is in its "Probably works" table (same chip). |
| Does our kernel already have the AWDL code? | Yes. The running `brcmfmac` (7.1.12-2-20261017.20-sep-ARCH, linux-aurora) exposes `awdl`, `awdl_bssid`, `awdl_trace`, and `/sys/module/brcmfmac/parameters/awdl` is 1. Its `interface_create.c`/`vendor.c` match `aurora-silicon/linux` `integration/aurora` (awdl_bssid mode 0444, no `awdl_create_flags`). `aurora-wip` carries the older shape with `awdl_create_flags`. |
| Do the helpers speak the kernel's protocol? | `userspace/brcm_iovar.py` and Aurora's `vendor.h` agree: vendor id `0x001018`, subcommand DCMD=1 and AWDL=2, AWDL ops CREATE=0 / DESTROY=1. Only op 2 (FWDUMP, firmware RAM snapshot, upstream patch 0010) is absent in Aurora; it is a diagnostic. |
| How close is Aurora to the upstream patch series? | omdrop-awdl's 14 patches apply cleanly (14/14) to its pinned Asahi tree. Diffing every `awdl` line against Aurora: `core.c`, `cfg80211.c`, `common.c`, `msgbuf.c`, `fwil.c`, `fwil_types.h` are identical to the patched tree on `aurora-wip`; `integration/aurora` differs only by the `awdl` on/off module parameter and a reformatted trace check. The only upstream code Aurora lacks is `p2p.c` action-frame forwarding (patches 0011-0013) and the FWDUMP op, i.e. instrumentation used by `awdl-resolve` / `--af-log`. |
| Do the helpers' own tests pass? | 168 passed, 2 skipped (run on the pristine upstream clone at the pinned revision). |
| Are awdl-up's preconditions met here? | Wi-Fi interface `wld0`, permanent MAC (`addr_assign_type 0`), `wifi.scan-rand-mac-address=no` (our `no-mac-addr-change.conf`), the active profile does not randomise. |
| Idle interface creation | PASS on 2026-10-18: `awdl-up` created `awdl0` on BCM4387 firmware `20.96.31.0.8.7.148`; Wi-Fi remained connected with 0% packet loss. |
| Visibility window | PASS on 2026-10-18: the 120-second window reached `visible=true`; the data-path gate needed three attempts (20/20 transmit completions on attempt 3). Wi-Fi stayed connected; latency rose while AWDL channel-hopped. |
| Receiver prerequisites | Current preflight passes, including `python3-libarchive-c`, `keyutils` and polkit. An actual transfer has not been tested. |
| Reboot availability | On 2026-10-22 the user systemd service was found disabled. `systemctl enable --now awdl0.service` restored persistent idle setup; service is active/exited, `awdl0` exists and NetworkManager marks it unmanaged. `omdrop doctor --json` now reports ready. |

## Not validated (needs the owner and a phone)

- Any actual transfer. Not receiving from an iPhone, not sending.
- The differences between the verified 16" and this 14" machine beyond the chip (same Wi-Fi chip, different board/NVRAM files).
- Upstream documents two firmware failure modes the helpers work around: a ~50% "parked" data path, and a firmware hang when `awdl=0` runs with a PSF template loaded (recovery is a driver reload, i.e. a reboot here). A hang would take Wi-Fi down until reboot; the dock Ethernet (`enx605b3042c174`) is the fallback link.
- Aurora's missing instrumentation (p2p action-frame forwarding): peer name resolution through `awdl-resolve` may be reduced; sending by device name needs checking.
- Contacts Only sending needs an Apple-issued AirDrop identity (upstream does not provide one); receiving from Everyone and from known senders does not.
