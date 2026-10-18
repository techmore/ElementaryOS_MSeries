# Factory YouTube fresh-install qualification — 2026-10-18

**Passed in an ARM64 KVM guest.** Build [39128555434](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39128555434)
produced `elementaryos-9.0-daily-arm64.20261018124553.iso` from
`5c0c60e7ff51dd97e093c02167c3de0686e71052`. Independent SHA256 verification passed:
`189f82fcc1eb78136c00f33c02c48e29877fd29d93b4bbf617bb2137c1060ba2`.
The ISO is retained as the workflow installer artifact, not committed to Git.

The live installer wrote a new blank 64 GiB virtual disk and exited zero.
The installed disk then booted with the ISO removed, using its default generic
7.0.0-38 UKI, without guest kernel edits or debug command-line overrides.
A synthetic account was created through graphical initial setup. `/usr` remained
read-only erofs. No browser packages were installed after boot, and no host
profile, account or directory was shared into the guest.

The actual installed desktop entry launched its private factory Brave 1.97.59.
The runtime manifest and `ldd` checks passed; `/opt` Brave was absent. The default
YouTube profile was absent at the passing launch. GTK resolved the system
`mseries-youtube` SVG with the same SHA256 as the source asset. Gala matched the
running movie window to `mseries-brave-youtube.desktop` and
`brave-www.youtube.com__-Default`, including after playback/navigation.

Anonymous public YouTube playback was measured through a temporary PATH shim
that appended only remote-debugging flags to the installed bubblewrap invocation.
The installed launcher, containment and decode flags were unchanged. The sample
was Blender's public [Big Buck Bunny video](https://www.youtube.com/watch?v=aqz-KE-bpKQ):

| Stream | Elapsed video time in ten seconds | Decoded frames | Decoded audio bytes |
| --- | ---: | ---: | ---: |
| Automatic 854×480 | 9.947494 s | 298 | 157,897 |
| Selected 1920×1080 | 9.967697 s | 599 | 156,917 |

Both intervals remained playing without a video error. Initial dropped frames
were 14 cumulative; the 1080p interval added 18. This is a playback check, not a
zero-drop performance claim. The host sound output was disabled.

The final [unedited guest screenshot](youtube-dock-playback.png) shows the movie
and the YouTube logo in the running dock item. The browser was resized so it did
not cover the default dock. Capture used the installed elementary Screenshot
application and its accessible Save button; QMP screendump cannot capture this
GL scanout. [qualification.json](qualification.json) preserves the measurements,
image identity, isolation arguments and screenshot hash.

The initial basic non-3D virtio GPU fixture failed Chromium dumb-buffer creation
before a window mapped. The same image mapped and played with virgl. Its failed
browser profile was archived before creating the empty default profile used for
the passing run. GTK4 introspection was not installed, so the observer used the
image's existing GTK3 introspection. Window mapping and document readiness were
polled before assertions. These were fixture/observer corrections, not changes
to the image under test.

The build ran with Fairydust and its tunnel disabled. This qualifies installation,
factory packaging, desktop identity/logo, and software video/audio decoding in
an ARM64 VM. Apple physical boot, V4L2 hardware decoding, DRM/Widevine and listening
quality remain unqualified by this run. Later unrelated main changes are not in
this ISO. The owned VM and receipt server were stopped after qualification.
