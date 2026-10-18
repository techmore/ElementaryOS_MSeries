# F5 dictation (local speech to text)

Hold **F5** (the microphone key), speak, release: the text is typed into the focused field of any app.
Voxtype 1.1.1 (MIT) + whisper.cpp `base.en` on the CPU, ydotool for typing (same stack as Omarchy).
Audio stays on the Mac; nothing is stored. Install: `bash mseries/install-dictation.sh` (`--uninstall` to remove).

Pieces
- `91-mseries-dictation.hwdb`: F5 becomes KEY_F14 (hid-apple otherwise makes it backlight-down). Supersedes the opt-in F5 remap in `90-mseries-keyboard.hwdb`.
- `aop-mic.sh` + `mseries-aop-mic.service`: the built-in mic (AOP, ALSA `hw:1,0`) is raw 3-channel **32-bit float** at 48 kHz (the driver advertises every format but always sends float); on this boot PipeWire has no node for it (see the 2026-10-18 fix section). The bridge publishes it as source `mseries-builtin-mic` (never auto-linked to speakers). Voxtype binds to it with `PIPEWIRE_NODE`.
- `config.toml`: hold-to-talk, `eager_processing` (4 s chunks transcribed while you talk). Copied once to `~/.config/voxtype/`.
- `STT-RESEARCH.md`: engine survey (Parakeet, Moonshine, MLX on Linux) and the staged upgrade plan.

Known gaps (2026-10-18)
- The live F5 round trip with a person speaking is **not yet verified**. Verified: key mapped to F14, service listening, bridge to Whisper end to end (a hiss recording transcribed as "Pshhh."), and offline speech through the same filter transcribed correctly.
- The mic bridge (`mseries-aop-mic`) is only used by the Voxtype fallback and is started on demand; streaming mode opens the mic only while F5 is held.
- Mic gain is 60 (`STREAM_GAIN` / `AOP_MIC_GAIN`) since the float fix below; typing assumes a US layout (ydotool).
- Grammar clean-up by a local LLM is a stub in `config.toml` (`[output.post_process]`), not tested.

## Streaming mode (2026-10-18, default after `install-dictation-stream.sh`)

Hold F5: words are typed while you talk instead of after you release. transcribe.cpp 0.4.0 (MIT) + Parakeet Unified 0.6B Q4_K_M (CC-BY-4.0) via `stream-dictate.py`; start/stop chimes; Voxtype stays installed as the fallback (`systemctl --user stop mseries-stream-dictate; systemctl --user start voxtype`).
Offline measurements on the 10.4 s LibriSpeech clip (3 warm runs, median, `stream-bench.py`, 6 threads): Parakeet Unified streaming RTF 0.29 on Vulkan (0.28-0.29 with private Mesa 26.2.4) and 0.37 on CPU, correct text with punctuation, first words about 3.3 s into speech, then roughly every second. Moonshine streaming small Q8_0 was too slow here (RTF 1.38 CPU, 1.56-1.68 Vulkan) and is not used.
**Not verified:** a live F5 session with a person speaking and text landing in an app; the mic hiss and the untuned gain may cost accuracy; words already typed are never corrected if the model revises them. Streaming needs an 8 s lead-in at most on first use for model load; model uses ~600 MB RAM while the service runs.

Streaming details: the mic (AOP `hw:1,0`) is opened by `stream-dictate.py` only while F5 is held (36 ms to first audio, measured); 3 raw channels are mixed, high-passed (120 Hz since the fix below), low-passed at 7 kHz and limited. The "-30 dBFS noise floor" measured here was the format bug described below, not the mic. 5 s of room silence typed nothing (2 runs); a "Listening…" notification and start/stop chimes mark recording. Rapid press/release cycles (0.4 to 2.5 s) reopened the mic cleanly. The grammar pass is not part of streaming: text is typed as it commits and is never retyped; Parakeet already outputs punctuation and capitals.

## Built-in mic fix (2026-10-18, branch `claude/dictation-finish`)

**What was broken.** The "mic sensitivity" blocker (owner's two F5 attempts at 05:56 recognized 0 characters) was a sample-format bug, not the mic. The AOP driver (`snd_soc_aop`) advertises every ALSA format but always delivers **FLOAT_LE**. ffmpeg's ALSA input defaults to `s16le`, so `stream-dictate.py` and `aop-mic.sh` read halves of floats as 16-bit samples: white noise at 0.5 std ("large DC offset", "channels uncorrelated", "-30 dBFS in-band noise"), with speech surviving only as a sign-bit shadow. The same bytes read as float are clean: room noise -76 to -79 dBFS per channel, laptop speakers playing speech -63 to -68 dBFS rms (peak -41 dBFS), channels 0.8-0.9 correlated.

**Changes.** ffmpeg now reads with `-c:a pcm_f32le` in `stream-dictate.py` and `aop-mic.sh`. Gain goes from 0.2 to 60 (+36 dB), and the high-pass from 150 to 120 Hz (asahi-audio uses 120 Hz and x120 for this array). The Whisper fallback gate (peak > 0.2, rms > 0.07, tuned on the noise) is now a speech-energy test: the spread between loud and quiet 100 ms chunks must be at least 8 dB, with at least 3 active chunks. `STREAM_QUIET` turns off the chime and notification, and `STREAM_TEST_RAW` replays a raw AOP capture through the real chain. The USR1 self-test must use `systemctl --user kill --kill-whom=main -s USR1 mseries-stream-dictate`: without `--kill-whom=main`, systemd also signals the ffmpeg capture child, which dies. The journal shows this happened in the earlier tests. New tools are `mic-eval.py` (raw capture, levels, WER over gains or chains on the same recording) and `test-dictation.py` (self-tests: a private, silent dry-run daemon driven by SIGUSR1; it never types, chimes or notifies).

**Evidence** (Parakeet Unified Q4_K_M, Vulkan, 6 threads; one run per row; reference is the LibriSpeech clip's transcript, 28 words):

| capture (clip through MacBook speakers, sink 0.66) | speech-band rms | stream WER | gate spread / active | Whisper base.en WER |
|---|---|---|---|---|
| room silence, 3 s | -82.9 dBFS | 0 words typed | 4.4 dB / 0 (no fallback) | not run |
| playback 1.0 | -67.4 dBFS | 0.0 % (gains 5-250: all 0.0 %) | 22.2 dB / 60 | 3.6 % |
| playback 0.316 (-10 dB) | -71.5 dBFS | 0.0 % | 17.4 dB / 46 | 7.1 % |
| playback 0.1 (-20 dB) | -79.0 dBFS | 3.6 % | 10.7 dB / 15 | 17.9 % (stopped after "carrots") |
| playback 0.0316 (-30 dB) | -83.1 dBFS (= noise) | 43-54 % | 2.6 dB / 0 | not run |

- Gain hardly changes Parakeet's WER, because the model normalizes level. Gain matters for the fallback gate, the "Didn't catch that" level and the Voxtype bridge.
- Tried at -20 and -30 dB, with no clear win: `afftdn` (39.3 % / 7.1 %), channel 2 only (32.1 % at -30 dB), and the asahi-audio triforce MVDR beamformer through ffmpeg's `lv2` filter (46.4 % / 3.6 %). The loopback source (the speakers) is not where a user sits, so beamforming is not judged by this test. Kept the plain mix.
- `test-dictation.py --loopback`, final live run: 9/9 PASS. Synthetic gate: noise 0.3 dB, worded tone 20.8 dB / 12, key click 0.3 dB / 1. Live mic is float32 (std 7-12e-5, mean < 2e-6). Offline clip: 0.0 % WER. Live 4 s room silence typed nothing (spread 1.4-4.2 dB, at most 1 active chunk, over 4 runs). 5/5 rapid press/release cycles reopened the mic. Live loopback: 0.0 % WER in 2 runs (peak 0.95-1.0, rms 0.070-0.076, spread 27.6-29.1 dB). Forced Whisper fallback: 7.1 % WER live; on saved captures 3.6 % (1.0), 7.1 % (-10 dB) and 17.9 % (-20 dB). The bar is 25 %, since the fallback is a last resort.
- Deployed: `~/.local/share/mseries/stream/stream-dictate.py` and `/usr/local/libexec/mseries/aop-mic.sh` updated, and `mseries-stream-dictate` restarted (active, model ready). The bridge command gives 2 s of room silence at rms 0.0049, peak 0.018 (the old path gave rms 0.035 of noise).
- Removed a leftover `pw-cat` test source ("test", node `mseries-test-mic`, started 05:20 by the earlier session) that was showing as a microphone in Sound settings.

**Not verified.** A person speaking into F5 with text landing in an app. A voice at normal distance is probably near the -10 to -20 dB rows, but that is not measured. The owner's next F5 attempt will tell: the service logs `peak/rms/floor/spread` per capture, and the existing `debug.conf` drop-in (`STREAM_KEEP=1`) keeps the last capture in RAM at `$XDG_RUNTIME_DIR/dictation-last.wav` (remove the drop-in to stop that). Also not verified: noisy rooms, and the Voxtype path end to end with the new bridge (the bridge conflicts with the streaming unit, so it was not started).

**Proposal (global audio, not done).** asahi-audio's default source `effect_output.j314-mic` (triforce beamformer, x80) is the system default microphone, but its input target `alsa_input.platform-sound.RawMics` does not exist on this boot: WirePlumber has card 1 (`AppleJ314HPAI`) on the HiFi profile with "availability unknown" and creates no capture node. So browsers and calls using the default mic most likely record silence. The mic was free when WirePlumber started (04:35; bridge first started 05:19), so a busy device is not the cause. Next step, which needs an owner-approved audio-stack change: after a WirePlumber restart or a re-login, check `pw-cli ls Node | grep RawMics`; if it is still missing, try `wpctl set-profile <card-1 device id> pro-audio` and back, and compare against upstream asahi-audio and WirePlumber 1.6.

## Universal insertion work — in qualification

The owner prioritizes universal speech-to-text before the troubleshooting and everyday assistant tiers. `dictation-input.py` registers an IBus input method and a session-bound commit interface. `dictation-input-client.py` passes transcript chunks over stdin and the session bus; it does not use the clipboard or synthesize keyboard-layout-dependent characters. The streaming source has an optional `STREAM_OUTPUT=ibus` route and Escape cancellation. The installed service is unchanged until app acceptance/deployment; the compatibility default remains ydotool.

A session expires after 120 seconds and rejects stale focus, password/PIN/private field hints, control characters and oversized text. Ordinary keys pass through. Applications must support/configure IBus and accurately report sensitive fields; this is not a claim of every Linux app or custom canvas working. It does not read surrounding text. Grammar/translation review remains pending.

Checks: `python3 -m unittest discover -s mseries/dictation -p test_input.py` (six contracts), then `dbus-run-session -- xvfb-run -a python3 mseries/dictation/ibus-context-smoke.py` (real isolated IBus Unicode commit, stale-focus refusal and password refusal). The latter uses its own bus/address, no microphone or owner windows. Initial harness/factory construction failures were corrected before its passing run. Observing the serialized wire signal avoids the PyGObject test-callback floating-object warning; GTK field tests pass without it. Actual GTK3 and GTK4 Entry tests passed Unicode, focus changes and password refusal; GTK3 also passed multiple chunks through the stdin client. Brave X11/XIM passed normal insertion and field-change refusal but failed password metadata reporting. XIM is now refused entirely, with a regression contract, pending a reliable browser route. This is a retained failed acceptance result, not universal app coverage. Qt/browser completion, live F5 and deployment remain pending. This input service has no model worker.
