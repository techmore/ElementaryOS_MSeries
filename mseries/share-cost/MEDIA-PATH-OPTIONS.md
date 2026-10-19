# Screen-share media path: options and decision gates

Decision support for "should the share media path change". The resource baseline
comes from [`collect-share-cost.sh`](collect-share-cost.sh); until that baseline
exists, no performance claim is justified.

## Owner decision — 2026-10-19

- **Media stays peer-to-peer.** Options B, C and D are rejected for this MVP.
  No screen-share media plane is to be built in `rupert-share`, TM-Remote, or
  anywhere else.
- **The work stays in this repository.** `ElementaryOS_MSeries` owns the
  share-cost harness, the panel integration and any Option A changes. The
  existing demo server is a dependency used to produce the baseline, not a new
  home for streaming work.
- **Option A is the only remaining candidate.** It still has to pass the
  matched-pair gate. If three viewers are not acceptable, the answer is to keep
  or lower the viewer cap, not to put media on a server.

## Current architecture

```
owner browser ──getDisplayMedia()──▶ xdg-desktop-portal / PipeWire picker
     │  (one RTCPeerConnection per viewer; the browser encodes per peer)
     ├──────────── P2P WebRTC media ────────────▶ viewer browser
     └── SDP/ICE signaling ──▶ rupert-core (Rust/axum, src/share.rs)
                                  links · admission · status/SSE · audit
```

No frame passes through the server today. That is the single property most
options below would change, so it is stated first. This diagram is the existing
demo stack used as-is to produce the baseline; this repository does not modify
it.

**Consent model (must not regress in any option):** three separate yeses — the
browser/portal picker chooses *what* is shared, the owner admits each viewer
individually (pending viewers receive nothing), and the link was made
deliberately. The existing demo server's own design note is the authoritative
description of that behavior; anything this repository builds keeps those three
or is rejected.

**Known limits today:** each additional viewer costs the owner's browser another
WebRTC encode chain (unmeasured — tracked as an open row by the demo project);
no TURN relay, so viewers behind symmetric NAT fail; viewer cap 8 (default 1);
a server restart ends every share; no recording.

## Option A — keep P2P; add TURN, surface the tailnet link, raise the caps

**Only remaining candidate (owner decision 2026-10-19).** Configuration and
panel-side additions, not an architecture change, and no new media plane in any
repository.

- **TURN relay** (coturn is the standard; a Rust TURN exists but is far less
  battle-tested) so hostile-NAT viewers can connect through the existing public
  proxy path. The demo server already accepts `RUPERT_SHARE_TURN*`; enabling
  coturn is deployment work, not new share code.
- **Tailnet link as its own labeled option.** `share-demo.sh --tailnet` already
  produces a tailnet address; the eyes menu currently shows it as "Local
  network". Surfacing it (Internet / Tailnet / Local network) is a panel change
  in `mseries/share-eyes-wingpanel` in this repository.
- Raise `RUPERT_SHARE_MAX_VIEWERS` only if the baseline says the browser copes.

Fixes reachability and link discoverability. Does **not** fix per-viewer encode
cost, recording, or headless sharing. Consent model untouched. Effort: small.
If the baseline shows three viewers are too expensive, this option shrinks to
the tailnet label and TURN; the cap stays where it is.

## Option B — Rust SFU with a browser simulcast uplink — **rejected**

**Out of scope by owner decision 2026-10-19: media must stay P2P.** Recorded
here only so the reasoning is not lost; do not implement this, and do not
reopen it without an explicit owner decision to let media transit a server.

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

## Option C — server-side capture and encode (headless) — **rejected**

**Out of scope by owner decision 2026-10-19: media must stay P2P.** No capture
daemon and no server-side encode is to be built in this MVP.

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

## Option D — run a stock SFU instead of building one — **rejected**

**Out of scope by owner decision 2026-10-19: media must stay P2P.** No stock
SFU is to be introduced for this MVP.

Self-hosted **LiveKit** (Go/Pion) for the media plane; `rupert-core` keeps
links, admission, status and audit; viewer pages move to the LiveKit JS SDK.

- Gets a battle-tested SFU with simulcast, recording and a TURN ecosystem, at
  the cost of a second service (and language) to operate and client-page
  rewrites. The consent/admission layer stays ours.

## Decision gates

1. **Owner-side CPU, 1 viewer vs 3 viewers**, matched pairs from
   `collect-share-cost.sh` (≥60 s arms, alternating, same content and display)
   and interpreted by `compare-share-cost.py`, which requires at least two
   captures per condition and applies the within-condition spread rule. This is
   the gate that decides whether Option A includes a viewer-cap raise.
2. **Whole-system watts** for the same arms on AC (SMC `power1_input`).
3. **Media on the server — resolved: no.** The owner rejected B/C/D on
   2026-10-19. Reopening this gate requires an explicit owner decision.
4. **Recording — not part of this MVP.** If it becomes required later, it is a
   separate owner decision and cannot use B/C/D without reopening gate 3.
5. **Project home — resolved: this repository.** `ElementaryOS_MSeries` owns the
   harness, the panel integration and any Option A change. No share media plane
   is to be built in `rupert-share` or TM-Remote.

## What "done" looks like for this MVP

- A matched 1-viewer/3-viewer pair from `collect-share-cost.sh` under the
  protocol above, with the medians and conditions recorded in this directory.
- Option A implemented only to the extent the pair supports: the tailnet link
  label in `mseries/share-eyes-wingpanel`, TURN as deployment configuration if
  NAT reachability is the problem being solved, and a viewer-cap raise only if
  the 3-viewer arm is acceptable.
- Consent regression suite: picker still required; a pending viewer receives no
  media; Stop and revoke end everything; locked-session refusal; no unnecessary
  rendering after sharing ends (the tracked gala issue's WebRTC acceptance
  list).
- Failure and soak: server restart ends the share; the panel returns to idle;
  external-monitor behavior unaffected.

## Recommendation logic

- **Measure first.** The harness exists; the pair has not been run. No option
  is justified today.
- **If 1 → 3 viewers is within acceptable CPU and watts:** implement Option A
  (tailnet label first), stop there, and do not revisit B/C/D.
- **If 3 viewers is not acceptable:** keep or lower the viewer cap. With media
  required to stay P2P, there is no acceptable server-side alternative; the
  answer is to share with fewer viewers.
- **If the requirements change** (recording, headless sharing, or a decision
  that media may transit a server), stop and take a new owner decision before
  writing any code.
