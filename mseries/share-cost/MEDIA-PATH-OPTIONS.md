# Screen-share media path: options and decision gates

Decision support for "should the share media path change, and would Rust help".
It does not pick an answer: it records the current architecture, what each option
would change, and the measurements that have to exist before choosing. The
resource baseline comes from [`collect-share-cost.sh`](collect-share-cost.sh);
until that baseline exists, every option below is a hypothesis.

## Current architecture

```
owner browser ──getDisplayMedia()──▶ xdg-desktop-portal / PipeWire picker
     │  (one RTCPeerConnection per viewer; the browser encodes per peer)
     ├──────────── P2P WebRTC media ────────────▶ viewer browser
     └── SDP/ICE signaling ──▶ rupert-core (Rust/axum, src/share.rs)
                                  links · admission · status/SSE · audit
```

No frame passes through the server today. That is the single property most
options below would change, so it is stated first.

**Consent model (must not regress in any option):** three separate yeses — the
browser/portal picker chooses *what* is shared, the owner admits each viewer
individually (pending viewers receive nothing), and the link was made
deliberately. `rupert-share/core/docs/SCREEN-SHARE.md` is the authoritative
description; anything built here keeps those three or is rejected.

**Known limits today:** each additional viewer costs the owner's browser another
WebRTC encode chain (unmeasured — the open row in
`core/docs/SCREEN-SHARE-TEST-TODAY.md`); no TURN relay, so viewers behind
symmetric NAT fail; viewer cap 8 (default 1); a server restart ends every share;
no recording.

## Option A — keep P2P; add TURN, surface the tailnet link, raise the caps

Configuration and small additions, not an architecture change.

- **TURN relay** (coturn is the standard; a Rust TURN exists but is far less
  battle-tested) so hostile-NAT viewers can connect through the existing public
  proxy path.
- **Tailnet link as its own labeled option.** `share-demo.sh --tailnet` already
  produces a tailnet address; the eyes menu currently shows it as "Local
  network". Surfacing it (Internet / Tailnet / Local network) is a panel change
  in `mseries/share-eyes-wingpanel`.
- Raise `RUPERT_SHARE_MAX_VIEWERS` if the baseline says the browser copes.

Fixes reachability and link discoverability. Does **not** fix per-viewer encode
cost, recording, or headless sharing. Consent model untouched. Effort: small.

## Option B — Rust SFU with a browser simulcast uplink

The publisher's browser sends **simulcast** (2–3 encodings in one uplink); a
media plane in `rupert-core` forwards a per-viewer layer to each admitted
viewer. Viewers stay ordinary browsers and still decode.

- **Why Rust fits:** an SFU forwards packets; it does not encode, decode or
  capture. That is routing and state — the same shape of work `rupert-core`
  already does, in the same binary. The server is already Rust/axum.
- **Crates:** `str0m` (sans-I/O WebRTC built for exactly this server role; no
  capture/encode/decode, which the browser side supplies) or `webrtc-rs`
  (pion-derived, full peer-connection API). `oxpulse-sfu-kit` (2026) adds
  multi-client glue on str0m — per-peer state, UDP routing, simulcast layer
  selection, bandwidth-adaptive switching — but is young; maturity would need
  its own assessment before adoption.
- **What it fixes:** viewer count stops scaling the owner's CPU (one uplink, N
  cheap downlinks); the viewer cap becomes bandwidth-bound; **recording becomes
  an egress tap** — a hidden subscriber writes the forwarded encoded frames, no
  re-encode.
- **What it changes (must be documented honestly):** media now transits the
  server. DTLS-SRTP terminates at the SFU, so "no frame ever passes through the
  server" becomes false, and the threat model's "not protected" list grows (a
  hostile server operator could see frames). The SFU becomes the availability
  and bandwidth center; viewers may need TURN to reach it. Admission must be
  enforced *before* any media flows, exactly as signaling is refused today.
- **Effort:** significant — media plane, simulcast negotiation, layer selection,
  bandwidth estimation, failure/soak paths — but no new encode cost on the M1
  Pro, because the publisher still encodes.

## Option C — server-side capture and encode (headless)

A Rust daemon takes the portal screencast session (`ashpd` /
xdg-desktop-portal) and the PipeWire stream, encodes once, and feeds the SFU.

- **Why consider:** no browser tab to keep open; survives browser restarts;
  consistent encode settings; recording trivial.
- **The catch on this machine:** Asahi exposes **no hardware video encoder**, so
  the encode is software (VP8/VP9/x264/SVT-AV1 via GStreamer or `ffmpeg-next`) —
  roughly a core or two for 1080p30, trading browser CPU for daemon CPU and
  watts. The consent surface also moves: the picker becomes a portal dialog
  driven by a daemon rather than the browser's own prompt, and "the browser's
  Stop sharing" signal disappears and needs a replacement owner stop path.
- **When it wins:** the baseline shows the browser path is expensive even at one
  viewer, or always-on/headless sharing is the real use case.

## Option D — run a stock SFU instead of building one

Self-hosted **LiveKit** (Go/Pion) for the media plane; `rupert-core` keeps
links, admission, status and audit; viewer pages move to the LiveKit JS SDK.

- Gets a battle-tested SFU with simulcast, recording and a TURN ecosystem, at
  the cost of a second service (and language) to operate and client-page
  rewrites. The consent/admission layer stays ours.

## Decision gates — what must be measured before choosing

1. **Owner-side CPU, 1 viewer vs 3 viewers**, matched pairs from
   `collect-share-cost.sh` (≥60 s arms, alternating, same content and display).
   If one viewer is already cheap and three is acceptable for the real use
   (1–2 trusted reviewers), Option A is the answer and the rest is unnecessary.
2. **Whole-system watts** for the same arms on AC (SMC `power1_input`).
3. **Is media-on-server acceptable to the owner?** Option B/C/D all change the
   documented threat model; A does not. This is an owner decision, not a
   technical one.
4. **Is recording actually required?** The upgrade survey lists recording under
   TM-Remote's `feat/webrtc` scope. If yes, B (tap), C, or D; if no, B's
   advantage narrows to viewer scaling.
5. **Which project is the home?** `rupert-share` holds the share backend today
   and the tracked issue says screen-sharing backend code stays in its intended
   project, not the retail core. TM-Remote (Go + Python gateway, recording and
   phone input) overlaps. Decide before building, so this does not become two
   systems.

## What "done" looks like for any option

- Matched before/after captures under the same protocol: owner CPU and watts,
  plus viewer-side quality and latency measured separately on the viewer's
  device (out of scope for the desktop harness).
- Consent regression suite: picker still required; a pending viewer receives no
  media; Stop and revoke end everything; locked-session refusal; no unnecessary
  rendering after sharing ends (the tracked gala issue's WebRTC acceptance
  list).
- Failure and soak: server restart ends the share; SFU crash does not leave a
  live-but-dead session; external-monitor behavior unaffected.
- Docs updated honestly — `core/docs/SCREEN-SHARE.md` threat model and limits,
  and the open CPU row in `core/docs/SCREEN-SHARE-TEST-TODAY.md` closed with
  numbers.

## Recommendation logic

- **Measure first.** The harness exists; the pair has not been run. No option
  is justified today.
- If viewer count is the real need and recording can wait: **B with str0m** —
  smallest consent change, no new encode cost, recording comes almost free
  later.
- If recording or headless sharing is required now: **C or D**.
- If the use stays one or two trusted viewers on LAN/tailnet: **A**, and stop.
