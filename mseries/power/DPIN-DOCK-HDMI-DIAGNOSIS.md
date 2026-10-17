# Dock HDMI (M1 Pro USB4 DP-IN) — diagnosis and staged experiment

> Historical snapshot on `power-usage`. Newer dock investigation lives on
> `docs/dock-video-decision`; see the [branch frontier and evidence gates](README.md#dock-hdmi-and-suspend)
> before using the experiments or status below as current guidance.

2026-10-17. Goal from the owner: **"success is we get HDMI in this dock working"**.

## Measured state of the running kernel

Dock: `WD22TB4 Thunderbolt Dock` on `port1` (left-front, the port Asahi documents for
displays), USB device `1d6b:0002 / 0bda:*` Dell-dock bridge, all Thunderbolt devices
`authorized=1`. Kernel `7.1.13-elementary-fairydust-usb4-dptunnel` booted on
`elementary-usb4-dpin-controlled` with `thunderbolt.allow_dp_tunnel=1
thunderbolt.dprx_bypass=1 thunderbolt.dprx_timeout=15000`.

The whole DP-IN chain is loaded and wired (`mux-apple-display-crossbar`,
`phy-apple-atc`, `phy-apple-dpin`, `appledrm`, `thunderbolt_apple`), and
`card2-DP-1` / `card2-HDMI-A-1` are `disconnected` while `card2-eDP-1` is connected
at 120 Hz. The DCPDPTXProxy path for the dock is `apple-dcp 28cc00000.dcp` (index 2,
`tunnel: 1`).

## The measured failure (dmesg, from the booted kernel)

```
apple-dpin b01e50000.phy: DP-IN activation failed: -67 (INACTIVE=0x0 ACK=0x1 HPD=0x0 STATUS=0x0 ENABLE=0x3)
apple-dcp   28cc00000.dcp: DPINDBG connect_source phy ret=-67 initialized=1 powered=0
apple-dcp   28cc00000.dcp: DPINDBG connect_source phy ret=0  initialized=1 powered=1
apple-dcp   28cc00000.dcp: DPINDBG tunnel_reply ret=0 powered=1 rate=0 lanes=4 link_error=0
apple-dcp   28cc00000.dcp: DPINDBG request_display ret=0
apple-dcp   28cc00000.dcp: DPINDBG hpd_work: hpd=1
apple-dcp   28cc00000.dcp: DPINDBG set_hpd hpd=1 afk_ret=-110
apple-dcp   28cc00000.dcp: DPINDBG hpd_work: E1 set_hpd(1) ret=-110 ignored (tunnel)
apple-dcp   28cc00000.dcp: DPINDBG apcall idx=22 dp_tunnel=1
apple-dcp   28cc00000.dcp: DPINDBG connect_source: waited=2986 ret=-67 powered=1 rate=0 lanes=4 link_error=-67
```

Reading against the driver source this pins down **two independent blockers**, and
the log captures the second one:

1. **The tunnel clock never starts.** `atcphy_tunnel_set_rate()` only does work when
   `rate != 0`: it enables `DPTX_PCLK1/2` and starts the AUSPLL, and polls
   `ACIOPHY_AUSPLL_LOCK` for up to 500 ms. Every `tunnel_reply` in the log reports
   `rate=0`, so the only rate the tunnel code has ever been asked for is 0 — no PLL,
   no PCLK. This matches `REA-DPIN-FINDINGS.md`: T6000 `initDPTunnel` decodes to
   `BTI c; RET` (a no-op), and the clock is only reached via
   `setLinkRate → configureDPTunnelMode`. `dptxport_call_get_max_link_rate()`
   hardcodes `LINK_RATE_HBR3`, but a real rate never arrives.

2. **The activation handshake bails the instant HPD reads low.**
   `apple_dpin_set_inactive()` returns `-ENOLINK` on the first HPD read, so it never
   waits for the ACK to clear. Apple's active transition is interrupt driven
   (`orReg(0x8, 0x3)` then wait on HPD, 1000 ms deadline). With no clock the ACK can
   never clear, so `HPD=0x0 ACK=0x1` is the log line that gets recorded.

Because `rate=0` (blocker 1) precedes and causes `HPD=0` (blocker 2), the two can only
be separated by experiment, which is what is staged here.

## Staged experiment (isolated; nothing shipped was overwritten)

`mseries/power/patches/0002-apple-dpin-tunnel-clock-and-hpd-wait.patch`:

* `phy_apple_dpin.force_tunnel_rate` (uint, Mb/s; `0` = off = shipped behaviour) —
  configures the tunnel clock from `dpin_init()`, i.e. before the handshake.
* `apple_dpin_set_inactive()` — waits for HPD instead of failing on the first low
  read, and still returns `-ENOLINK` if HPD drops after having been seen (a real link
  loss) or `-ETIMEDOUT` at the 1000 ms deadline.

Built from a `.git`-less copy of the DP-IN tree so the vermagic is exactly
`7.1.13-elementary-fairydust-usb4-dptunnel SMP preempt mod_unload aarch64`, repacked
into a **new** initramfs (`initramfs-linux-asahi-fairydust-usb4-dpin-clock.img`) that
replaces only `phy-apple-dpin.ko` + `phy-apple-atc.ko` and preserves all 1120 other
entries. The existing DP-IN images are untouched.

* Boot entry `elementary-usb4-dpin-clock` (armed as `next_entry`), i.e. the running
  kernel + `thunderbolt.*` identical + `phy_apple_dpin.force_tunnel_rate=8100`.

## What the next boot tells us

`sudo dmesg | grep -iE 'dpin|tunnel_reply|hpd|DP-IN'`

| Observation | Conclusion |
| --- | --- |
| `forced tunnel rate 8100 Mb/s configured`, then `tunnel_reply ... rate=8100`, then HPD rises and `DP-1`/`HDMI-A-1` become `connected` | blocker 1 was the cause — port the clock start into the real link-rate path |
| `forced tunnel rate ... configured` but `HPD` still low and `DP-IN activation failed` | blocker 1 is fixed in isolation, blocker 2 (or something further) remains |
| clock starts but `AUSPLL` never locks (`forced tunnel rate ... failed: -110`) | the tunnel AUSPLL descriptor `APPLE_ATC_TUNNEL_DESC_*` is wrong for this port/phall and needs re-derivation |

`dprx_bypass=1` is a param of the *shipped* experiment and is not proof of a DPRX or
DPCD response (`REA-DPIN-FINDINGS.md`), so it does not change the meaning of this test.

## Other artifacts in this tree

`mseries/power/DYNAMIC-REFRESH-AUDIT.md` + `patches/0001-appledrm-adaptive-sync.patch`
separable ProMotion/VRR experiment (built, staged as `elementary-usb4-vrr`).
