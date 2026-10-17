# Orchard for Incus

Native GTK 4 manager for Incus containers/VMs on the M-series desktop,
modelled on [andrew-waters/orchard](https://github.com/andrew-waters/orchard)
(MIT, © Andrew Waters; reviewed at `2c78257c8602ffed61f383ee6e737bfc37b142ee`).
Orchard is a SwiftUI app for Apple's `container` tooling, so this is an
independent reimplementation that drives the `incus` CLI; no upstream code is copied.

Features: live instance list (state, type, image, IPv4, memory, processes),
start/stop/restart, shell (elementary Terminal), info + log viewer, snapshot,
delete (confirmed), create container or VM from any image.

Not yet ported: dashboard graphs, compose, Kubernetes, local-AI sandboxes,
profiles/networks/storage views.

Run: `./orchard-incus`. Install: copy to `/usr/local/bin` and the
`.desktop` to `/usr/share/applications`. Requires `python3-gi`, GTK 4, `incus`
access for the user (group `incus-admin`).
