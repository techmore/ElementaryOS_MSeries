# On-device Siri-like assistant on LFM3-Audio-2B

## Goals

1. **Inline suggestions in any text field.** Type, press **F6**, see a continuation, press **Tab** to insert it, Esc to drop it.
2. **Universal dictation**, as on a Mac. Tap **F5** in any field, talk, and the words stream in. Tap F5 again to stop.
3. **A Siri-like assistant app.** Talk or type. It answers by voice and text, and it can act: open apps, run tasks and call tools, with your approval for anything that has side effects.
4. **Smart Reply, kept separate:** chat replies (Ctrl+Alt+R, already built) and form filling, as distinct features on the same model.

Everything runs on the laptop. One model, [LiquidAI LFM3-Audio-2B (MLX 8-bit)](https://huggingface.co/LiquidAI/LFM3-Audio-2B-MLX-8bit), handles text, speech recognition, speech output and speech-to-speech. Only one assistant model is resident (about 2.5 GB).

## What already exists (reuse, don't rebuild)

| Piece | Where | State |
|---|---|---|
| F5 streaming dictation into any field | `mseries-stream-dictate.service` (Nemotron/Parakeet streaming, toggle mode) + IBus bridge `mseries-dictation-input.service` (`mseries/dictation`) | Works, owner-accepted. Was found not running this session, which is being fixed in this PR series. |
| Hold-a-draft input method (Tab inserts, Esc drops, password/unknown fields refused, previous IME restored) | `rust/mseries-reply` (`ibus.rs`, `held.rs`) | Works; used by Smart Reply |
| AT-SPI field and window reading, bounded and deadline-guarded | `rust/mseries-reply` (`a11y.rs`, `tree.rs`, `window.rs`) | Works |
| Smart Reply chat drafts (Ctrl+Alt+R) with personal memory | `rust/mseries-reply`, `rust/mseries-ai` | Works on Qwen 4B |
| Typed OS tools over MCP (tasks, calendar, notes, app inventory, faults; no shell) | `mseries/local-ai/os-mcp.py` | 16 tools |
| Broker / agent-first design, risk classes, grants | `mseries/local-ai/PANTHEON-MCP-DESIGN.md`, `mseries/SDK-AGENT-SURFACE.md` | Design |
| Private Vulkan MLX runtime (omarchy-mlx v0.7.33) and quiet/memory policy | `~/.local/share/mlx-omarchy`, `mseries/local-ai/machine.py` | Works |
| Runtime tuning findings: Vulkan work budget, prompt-cache reuse, ANE status | PR #648 (`codex/tensorfold-vulkan`) | Measured; ANE not yet device-tested |

## Measured on this M1 Pro (Oct 27)

LFM3-Audio-2B 8-bit runs on the private Vulkan MLX through mlx-vlm at commit `efd4b9f` (LFM3-Audio support, Blaizzy/mlx-vlm#2609; no release yet):

- Load 3.4 s; peak memory 2.5 GB.
- Speech-to-text, 10 s LibriSpeech clip: exact transcript in 1.9 s.
- Text-to-speech, 3.5 s of speech: 5.4 s.
- Inline completion: 1.0–1.6 s warm ("The meeting tomorrow has been moved to" → " 2:00 PM.").
- Chat: 0.6 s for a one-line answer once the empty think block is prefilled.
- Vulkan work budget `MLX_OMARCHY_BATCH_WORK=20000`: suggestions 7% and speech-to-text 13% faster than the default; 80k adds about 2 points. 20k is used.

Best tool per job: F5 live dictation stays on the streaming Nemotron/Parakeet path, because it types words while you talk. LFM3-Audio handles voice-chat input, multilingual transcription, spoken answers, suggestions and Smart Reply, replacing the 6.5 GB Qwen 4B for those.

## Architecture

```
F5 ──► stream-dictate (Nemotron, streaming) ──► IBus dictation bridge ──► any field
F6 ──► mseries-reply suggest ──► AT-SPI: text before caret ─┐
Ctrl+Alt+R ──► Smart Reply (chat) ──────────────────────────┤
Assistant app (talk/type) ──────────────────────────────────┼──► mseries-assistd :8772 ──► LFM3-Audio-2B (MLX/Vulkan → ANE later)
                                                            │         /v1/complete  /v1/chat/completions
held draft ◄── IBus Smart Reply engine (Tab inserts) ◄──────┘         /v1/audio/transcriptions  /v1/audio/speech  /v1/assist/voice
Assistant app ──► agent loop ──► desktop MCP server (apps, windows, AT-SPI, typed adapters) ──► approval UI + audit log
```

1. **Model runtime: `mseries-assistd`** (`mseries/assistant/assistd.py`). One per-user service on loopback. It loads on first use, unloads after 10 idle minutes, and refuses to load below the 6 GiB desktop reserve plus 3 GiB. It keeps per-mode prompt caches and exposes an OpenAI-style chat API, so existing clients (`mseries-ai`) work unchanged. The backend sits behind one class, so the ANE path can replace MLX/Vulkan once omarchy-ane and ane-linux-experiments qualify LFM3.
2. **Text-box integration.** Suggestions and Smart Reply use the existing Smart Reply IBus engine. Display and commit stay separate, because IBus preedit is unsafe in Chromium. Dictation keeps its own bridge. Both refuse password, card, one-time-code and unknown fields, terminals and password managers.
3. **Assistant app.** A Rust/GTK4 Pantheon app following the SDK conventions (`rust/msdk`, `mseries/APP-BUILDING-GUIDE.md`). It has push-to-talk and a text box, streams text, plays the spoken answer, shows each proposed tool call as a card with Run / Cancel, and keeps a history. A global shortcut opens it.
4. **Agent action layer: desktop MCP server.** Grow `os-mcp.py` into a Rust `mseries-desktop-mcp` that borrows the useful parts of [Cua Driver](https://cua.ai/docs/cua-driver):
   - The tool set: `list_apps`, `launch_app`, `list_windows`, `focus_window`, `get_window_state` (AT-SPI tree), `click`/`set_value`/`press_key` through AT-SPI actions first, `type_text` through the IBus commit path, and `clipboard_read`/`clipboard_write`. The existing typed adapters stay (tasks, calendar, notes, mail drafts). No generic shell.
   - Every action names an explicit target (pid plus window) and returns a structured result: `confirmed`, `unverifiable` or `refused` plus a reason code. Results are verified by reading the accessibility tree back; an "ok" is not trusted.
   - Perception is bound to a capture id with a short lifetime, so stale screens are refused.
   - A deny-by-default capability manifest per tool, app and path, with length and regex limits on typed text. The daemon owns grants, and the model cannot widen them.
   - A trajectory log for audit, and batched steps with an observation to cut round trips for a small model.
   - **Why not cua-driver itself.** It is MIT and well designed, but its Linux support is x86_64 desktops only (X11; Wayland is compositor-specific and refuses raw background keys). This laptop is aarch64 with Pantheon's own compositor, so we write a Rust driver with the same contract instead. The design points we copy:
     - Never steal focus. The ladder is AT-SPI action first, then IBus text commit, then compositor-addressed input, with foreground delivery only as an explicit, logged last resort.
     - Sessions are per MCP connection and reaped after 5 idle minutes.
     - Stdio MCP is the default. A shared daemon listens on a unix socket. HTTP is off unless enabled, and then needs a bearer token.
     - Permission layers: admin policy, then user policy, then mode (standard, bounded or unrestricted), then a per-session manifest with `allow.tools`, `resources.apps/files/browser` and `expires_after`.
     - Browser actions only through typed `browser_*` tools over CDP against the separate Assistant Browser profile.
     - Pantheon gives us an advantage cua-driver lacks: the compositor already exposes `org.pantheon.gala` window lists, and SDK apps can publish their own semantic tree (`msdk render`). Prefer those over pixels.
   - **Sandbox VMs for risky actions** (the idea from [Lume](https://cua.ai/docs/lume), which runs only on macOS hosts). Use qemu/KVM, which already works here (`/dev/kvm`, ARM64 guests, `~/vms/elementary`, `mseries/KVM-VMS.md`).
     - Keep a golden elementary OS ARM64 image. Each risky task gets a throwaway qcow2 overlay plus its own copy of the UEFI vars, and the clone is discarded afterwards.
     - Shares are read-only by default. No credentials in the golden image. The control channel is loopback or virtio-vsock only.
     - Use it for running untrusted scripts, trying installs or config changes, and opening unknown files or links. The assistant reports the diff or result, and you choose whether to apply it on the host.
     - The same driver runs inside the guest, so one tool contract works for both.
5. **Safety.** Window and field content is data, never instructions. Read-only tools run freely. Local reversible creates run under a standing grant. Sending, deleting and system changes need a visible confirmation of the exact action.

## Milestones

- **M1: model service and F6 suggestions (this PR).** `mseries-assistd` with all endpoints, the `mseries-reply suggest` command bound to F6, the installer, and the F5 dictation startup fix.
  - *Accept:* the service starts at login and is idle until used. F6 in a GTK, Qt and Chromium field shows a suggestion within about 2 s warm; Tab inserts it and Esc drops it. Password fields and terminals are refused. F5 dictation is running after a fresh login.
- **M2: Assistant app (talk and type).** Chat UI, push-to-talk through `/v1/assist/voice`, spoken answers, history, and a global shortcut.
  - *Accept:* a spoken question gets a spoken and written answer within 4 s on a warm model. Typed chat works with the mic off. The app passes the HIG/SDK app checks.
- **M3: agent actions over MCP.** `mseries-desktop-mcp` with the Cua-style tools above, tool calling from LFM3, approval cards and the audit log.
  - A sandbox tool (`sandbox_run`) clones the golden VM, runs the task there with the same driver, returns the result, and discards the clone.
  - *Accept:* "open Files", "make a task to call Jan tomorrow at 3" and "what's using my battery?" each work by voice. "Try this install script" runs only in a throwaway VM. Every side effect is shown before it runs, and refusals come back structured.
- **M4: Smart Reply on LFM3, plus Forms.** Move Ctrl+Alt+R drafts to assistd as an option. Add a separate form-fill mode that proposes values per field from the owner's profile, never for password or card fields.
  - *Accept:* draft quality is at least as good as Qwen 4B on the existing reply fixtures. A form fill proposes and never submits.
- **M5: speed and the ANE.** Adopt TensorFold's one-submit-per-token batching when it is public (30–40% on M1 parts), and the omarchy-mlx updates past v0.7.33. Run the LFM3 backbone on the ANE when the Linux ANE path is device-qualified (see PR #648's handoff).
  - *Accept:* a paired, matched before/after on suggestion and speech-to-text latency, with identical output.
- **M6: opt-in automatic suggestions** after a typing pause, with per-app rules (off by default).

## Out of scope for now

Cloud models, wake word, screen capture for vision (no compositor capture path yet), and multi-user setups.
