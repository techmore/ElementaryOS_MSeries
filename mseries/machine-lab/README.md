# Machine Lab

Native elementary OS look (Vala + GTK 4 + Granite 7) for running another Linux ARM64
guest under QEMU/KVM with NAT networking. Flat sidebar of machines, hero header, spec cards,
drag-and-drop installer picker, Start/Force Stop with live status, toast feedback, and
light/dark + accent following the system.

```sh
meson setup build && meson compile -C build
./build/machine-lab        # finds ../launcher/run-vm.sh, or set MACHINE_LAB_LAUNCHER
```

Launcher and known gaps: `launcher/README.md`. Moved here from the Codex native-vm-poc spike.
Visual check was done headless via GTK Broadway; not yet launched on the desktop or booted with a guest ISO.
