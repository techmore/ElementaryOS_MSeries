# AirDrop radio test plan (j314s). Run with the owner at the keyboard and a phone in hand.

Stop at the first step that fails. Every step says how to undo it. No step changes the driver, the bootloader or the kernel.

Before you start: no live screen share; the dock Ethernet (`enx605b3042c174`) plugged in as a fallback link; the iPhone's AirDrop set to **Everyone for 10 Minutes**; `git` checkout at branch `claude/airdrop-omdrop`.

0. **Preflight** (read-only): `bash mseries/install-omdrop-radio.sh preflight`. Needs `sudo apt install python3-libarchive-c` first; expect "PREFLIGHT OK".
1. **Install the files and idle interface**: `bash mseries/install-omdrop-radio.sh install`. The installer reloads NetworkManager's config, then enables and starts `awdl0.service`. Expect `awdl0` to exist while AirDrop remains off and invisible. Check Wi-Fi stays connected. Undo: `bash mseries/install-omdrop-radio.sh uninstall`.
2. **Open a 2-minute window, no files**: `pkexec /usr/lib/omdrop/omdrop-discoverable start 120`, then `/usr/lib/omdrop/omdrop-discoverable status --json` (expect `visible: true`; `rx_proven` may stay false until frames arrive), then `pkexec /usr/lib/omdrop/omdrop-discoverable stop`. Watch Wi-Fi throughput: it is expected to dip while the window is open (channel hopping). Undo: `stop`.
3. **Receive from the iPhone** (Everyone): `omdrop on once`, then on the iPhone share a photo to the Mac named by `omdrop status`. Expect a notification and the file in `~/Downloads`. Also try it from the Quick Settings AirDrop row after a Wingpanel reload (the switch runs the same command).
4. **Send to the iPhone**: `omdrop peers -n` then `omdrop send ~/some.jpg <name>`. If names are missing (Aurora lacks the action-frame instrumentation), use `--to ADDRESS`.

Record the outcome of each step, the firmware line (`journalctl -k -b | grep Firmware`) and any `FAIL`/hang in `mseries/OS9-HANDOFF.md`. Report a failing step upstream with the capture from step 3.
