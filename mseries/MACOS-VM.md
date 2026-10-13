# macOS guests on Asahi Linux

Not currently possible. A macOS guest on Apple Silicon needs Apple's Virtualization/Hypervisor frameworks and
Apple's virtual hardware (paravirtual GPU, storage, boot ROM handling), which exist only on macOS hosts. Linux KVM
on the M1 Pro does not provide them, and no open implementation boots macOS under it. Options that do work:

- Linux arm64 guests under KVM (QEMU/virt-manager) once KVM is enabled for the running kernel.
- Dual boot: the internal macOS stays installed; pick it at the boot picker (hold power) or `asahi-bless --set-boot-macos`.
- A macOS VM from a Mac that runs macOS (UTM/Tart/Virtualization.framework), reached over the network.
