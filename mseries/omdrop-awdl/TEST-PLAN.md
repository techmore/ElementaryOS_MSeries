# AirDrop radio test plan (j314s). Run with the owner at the keyboard and a phone in hand.

Stop at the first step that fails. Every step says how to undo it. No step changes the driver, the bootloader or the kernel.

Before you start: no live screen share; the dock Ethernet (`enx605b3042c174`) plugged in as a fallback link; the iPhone's AirDrop set to **Everyone for 10 Minutes**; `git` checkout at branch `claude/airdrop-omdrop`.

0. **Preflight** (read-only): `bash mseries/install-omdrop-radio.sh preflight`. Needs `sudo apt install python3-libarchive-c` first; expect "PREFLIGHT OK".
1. **Install the files only**: `bash mseries/install-omdrop-radio.sh install`. Expect "awdl0 was NOT created". Check: `omdrop doctor` now reports one fewer missing item (the driver line is gone or changes). Undo: `bash mseries/install-omdrop-radio.sh uninstall`.
2. **Tell NetworkManager to leave awdl0 alone** (only config, no restart of Wi-Fi): `sudo nmcli general reload conf`. Check Wi-Fi still connected.
3. **Create awdl0, idle** (first radio touch): `sudo /usr/lib/omdrop/awdl-up`. Expect awdl0 to appear with a link-local address, AWDL still off, Wi-Fi still connected (`ping -c3` over Wi-Fi before and after). Capture: `ip -6 addr show awdl0`, `journalctl -k -n 40 | grep -i -E 'brcmf|awdl'`. Undo: `sudo python3 /usr/lib/omdrop/brcm_iovar.py -i wld0 awdl-if destroy`. If Wi-Fi drops, use Ethernet and reboot (a driver reload is the only recovery upstream documents).
4. **Open a 2-minute window, no files**: `pkexec /usr/lib/omdrop/omdrop-discoverable start 120`, then `/usr/lib/omdrop/omdrop-discoverable status --json` (expect `visible: true`; `rx_proven` may stay false until frames arrive), then `pkexec /usr/lib/omdrop/omdrop-discoverable stop`. Watch Wi-Fi throughput: it is expected to dip while the window is open (channel hopping). Undo: `stop`.
5. **Receive from the iPhone** (Everyone): `omdrop on once`, then on the iPhone share a photo to the Mac named by `omdrop status`. Expect a notification and the file in `~/Downloads`. Also try it from the Quick Settings AirDrop row after a Wingpanel reload (the switch runs the same command).
6. **Send to the iPhone**: `omdrop peers -n` then `omdrop send ~/some.jpg <name>`. If names are missing (Aurora lacks the action-frame instrumentation), use `--to ADDRESS`.
7. **Boot behaviour** (optional, later): `sudo systemctl enable awdl0.service` only after steps 3-6 passed. Undo: `sudo systemctl disable awdl0.service`.

Record the outcome of each step, the firmware line (`journalctl -k -b | grep Firmware`) and any `FAIL`/hang in `mseries/OS9-HANDOFF.md`. Report a failing step upstream with the capture from step 3.
