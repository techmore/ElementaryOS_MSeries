# F5 dictation (local speech to text)

**Current English-only decision, October18:** [measured native ANE / MLX Vulkan /
CPU streaming results](REALTIME-ENGLISH.md) supersede older recommendations below.
Nemotron160 CPU produced first draft words in0.851s median; MLX Vulkan
Parakeet1.452s; the existing ANE controller2.97s warm committed output. All
retained the six-GiB reserve and stayed below2532RPM in these limited public-file
trials. Output policies differ; these are not universal accuracy or live F5
claims. A private native English panel showed raw words and optional English
grammar suggestions during speech. The English-only source is on draft PR155;
no runtime or owner preferences changed in this benchmark. Earlier
foreign-language probes are historical, outside the owner's clarified scope.
Candidate deployment, lifecycle gates and human F5 acceptance remain open.

Hold **F5** (the microphone key), speak, release: the compatibility service types recognized text into the focused field. Cross-app support and current limits are qualified below.
Voxtype 1.1.1 (MIT) + whisper.cpp `base.en` on the CPU, ydotool for typing (same stack as Omarchy).
Audio stays on the Mac and is not saved by default. The explicit `STREAM_KEEP` debug option saves the last capture in the runtime directory; those recordings are private and excluded from published receipts. Install: `bash mseries/install-dictation.sh` (`--uninstall` to remove).

Pieces
- `91-mseries-dictation.hwdb`: F5 becomes KEY_F14 (hid-apple otherwise makes it backlight-down). Supersedes the opt-in F5 remap in `90-mseries-keyboard.hwdb`.
- `aop-mic.sh` + `mseries-aop-mic.service`: the built-in mic (AOP, ALSA `hw:1,0`) is raw 3-channel **32-bit float** at 48 kHz (the driver advertises every format but always sends float); on this boot PipeWire has no node for it (see the 2026-10-18 fix section). The bridge publishes it as source `mseries-builtin-mic` (never auto-linked to speakers). Voxtype binds to it with `PIPEWIRE_NODE`.
- `config.toml`: hold-to-talk, `eager_processing` (4 s chunks transcribed while you talk). Copied once to `~/.config/voxtype/`.
- `STT-RESEARCH.md`: engine survey (Parakeet, Moonshine, MLX on Linux) and the staged upgrade plan.

Known gaps (2026-10-18)
- The live F5 round trip with a person speaking is **not yet verified**. Verified: key mapped to F14, service listening, bridge to Whisper end to end (a hiss recording transcribed as "Pshhh."), and offline speech through the same filter transcribed correctly.
- The mic bridge (`mseries-aop-mic`) is only used by the Voxtype fallback and is started on demand; streaming mode opens the mic only while F5 is held.
- Mic gain is 60 (`STREAM_GAIN` / `AOP_MIC_GAIN`) since the float fix below; typing assumes a US layout (ydotool).
- Automatic streamed grammar remains disabled; optional original/proposal review is qualified separately below.

## Streaming mode (2026-10-18, default after `install-dictation-stream.sh`)

Hold F5: words are typed while you talk instead of after you release. transcribe.cpp 0.4.0 (MIT) + Parakeet Unified 0.6B Q4_K_M (CC-BY-4.0) via `stream-dictate.py`; start/stop chimes; Voxtype stays installed as the fallback (`systemctl --user stop mseries-stream-dictate; systemctl --user start voxtype`).
Offline measurements on the 10.4 s LibriSpeech clip (3 warm runs, median, `stream-bench.py`, 6 threads): Parakeet Unified streaming RTF 0.29 on Vulkan (0.28-0.29 with private Mesa 26.2.4) and 0.37 on CPU, correct text with punctuation, first words about 3.3 s into speech, then roughly every second. Moonshine streaming small Q8_0 was too slow here (RTF 1.38 CPU, 1.56-1.68 Vulkan) and is not used.
**Not verified:** a live F5 session with a person speaking and text landing in an app; human speech accuracy still needs confirmation; words already typed are never corrected if the model revises them. Streaming needs an 8 s lead-in at most on first use for model load; model uses ~600 MB RAM while the service runs.

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

## Universal insertion — installed, human trial pending

The installed IBus bridge commits Unicode text without the clipboard or keyboard-layout-dependent key synthesis. It binds a 120-second session to one focused field, rejects control characters/oversized text and supports Escape cancellation. It now requires both input-method hints and AT-SPI focused-field role/state/identity plus an active top-level window. It does not request surrounding text. Password, unknown/inaccessible and non-editable fields are refused. Qt top-level QWidget containers are recognized through their application parent.

The first browser trial incorrectly accepted a password-field session using input-method hints alone. That failure remains in [the original receipt](../local-ai/receipts/dictation-input-2026-10-18/qualification.json); the separate revised receipt records the stronger metadata gate. No password text was inserted by that failed test. The fix applies to every client, not only XIM. Browser tests explicitly enable accessibility; this does not establish support in an existing browser lacking that metadata.

| Current revised-source checks | Result |
|---|---|
| Sixteen session/deployment/status/resource contracts | Pass |
| Real IBus context without an accessible field | Refused as required |
| GTK3 X11 Entry, multi-chunk stdin client, changed field, password | Pass |
| GTK4 native Wayland Entry in separate headless Gala | Pass |
| Qt6 X11 QLineEdit/QTextEdit, Unicode/multiline, changed field, password | Pass |
| Brave X11 synthetic form with accessibility enabled | Pass |
| Electron 44.4.5 synthetic form with explicit accessibility | Pass (framework, not an actual Codex/OpenCode session) |
| Terminals/custom canvases, live human F5 | Pending; no universal coverage claim |

Run `python3 mseries/dictation/gtk-input-smoke.py`, `python3 mseries/dictation/qt-input-smoke.py` (PyQt6 test dependency), `python3 mseries/dictation/browser-input-smoke.py`, and `bash mseries/dictation/test-wayland-input.sh`. X11 tests create private session buses/Xvfb automatically; the native Wayland wrapper creates its own headless software-rendered Gala with memory-backed settings. They do not capture audio, run ASR, change the owner engine or use owner profiles. Private full logs stay out of receipts. Transient private portal/AT-SPI cache startup warnings remain in logs; the original Python signal callback floating-object warning was avoided by wire-level testing and was absent from real field checks.

The CPU/IBus services are **activated and ready**. Actual stage-only rollback preserved the original F5 process, and a later full activation/rollback/reactivation cycle restored original files and preferences. The retained early activation and restore-order failures precede those fixes. A person speaking through F5 into an app remains unverified. Owner edits after staging are preserved by digest checks. Active capture/output children are checked across every worker thread; dead notification children do not block switching.

The bridge now acquires the Dictation engine only for an explicit F5 session and restores the previous engine after queued output finishes or Escape cancels. A deliberate layout change wins over automatic restoration. Existing keyboard source lists are untouched; no IBus restart or static registry edit is needed. Permanently selecting the dynamic engine failed because the [upstream keyboard indicator](https://github.com/elementary/panel-keyboard/blob/main/src/PopoverWidget.vala) reapplies the configured layout. The failed permanent-selection rollout is retained with that limitation, rather than called a desktop usability pass.

Session-scoped checks pass GTK3 X11 (including ordinary keys, Shift, Backspace and dead-key composition), native GTK4 Wayland, Qt6 single/multiline, Brave and an Electron 44.4.5 synthetic form. They cover original-engine restore and changed-field/password refusal; GTK also covers overlapping Begin rejection and preservation of an owner layout change. The first browser session attempt lacked startup metadata and failed closed; the revised fixture waits for the initial accessibility event without retrying a rejected Begin. Actual Codex/OpenCode sessions are not established by a synthetic Electron form.

The changed session/queue path was checked once through CPU ASR on the same public English clip: 0% normalized WER, first text 5.09 s, total 12.61 s, minimum available 9.00 GiB, maximum sampled fan 2523 RPM and temperature 49.29 C. This is a new integration revision, not a repeat scored to improve earlier results. The everyday model independently stopped on its memory-reserve guard during this mixed-workload period; this trial does not establish simultaneous model residency. Its enabled service awaits adequate admission headroom.

To reproduce the file path, use `python3 mseries/dictation/gtk-input-smoke.py --keyboard-check --speech-file "$HOME/.local/share/mseries/stream/libri.wav" --receipt-dir /a/new/private/output` with the existing benchmark clip. This explicit option runs CPU ASR; default field commands do not.

The guarded CPU speech-to-field check passed on one existing LibriSpeech English clip (CC-BY-4.0): 0% normalized WER, first widget text 4.31 s including cold process/model startup and paced input, total 12.02 s, min available 11.55 GiB, max sampled fan 2525 RPM and temperature 45.76 C. The earlier source revisions are retained separately. These are functional/sampled results, not acoustic measurements, general speech accuracy or a controlled CPU/GPU ranking. Exact evaluated source, model/SDK pins and failures are in [receipts](../local-ai/receipts/dictation-input-2026-10-18/). [Corpus attribution/license](https://www.openslr.org/12).

Unicode activation uses CPU ASR so it does not add a competing GPU inference worker. It shares the six-GiB memory reserve and hard fan/temperature limits, waits before loading when admission fails, checks before recording and stops its own session on a limit violation. Other owner jobs are preserved. Recording status is a private bounded lifecycle file and persistent notification; Escape cancels. No text/audio is stored in that status. Whisper fallback uses an anonymous RAM descriptor, independently checked with the real CLI. Optional STREAM_KEEP debug capture remains explicit; full logs/debug audio are never public receipts.

Existing pinned runtime:

```sh
python3 mseries/install-dictation-input.py --stage
python3 mseries/install-dictation-input.py --activate
python3 mseries/install-dictation-input.py --status
python3 mseries/install-dictation-input.py --rollback
```

A fresh runtime can use `bash mseries/install-dictation-stream.sh --universal`. Installation pins the qualified NumPy 2.5.4 alongside transcribe.cpp 0.4.0. Activation enables toolkit accessibility, installs IBus environment defaults for future sessions and configures direct Brave launcher entries to enable accessibility on their next launch. It does not enable a screen reader, close a running browser or change audio routing. Existing Chromium instances without accessibility metadata remain unsupported until reopened; OS accessibility alone was insufficient in the retained default-browser test. Custom launcher wrappers are preserved. Other app launches can use `python3 ~/.local/share/mseries/stream/dictation-launch.py [--chromium] APP...`; flags affect new instances. Qt/GTK environments and actual app support still require the documented checks, not an all-app promise.

Backups and preference baselines remain private. Rollback restores prior settings when they still match this feature's values, preserves subsequent owner edits and waits for quiet admission before reloading speech. Remaining: owner F5 confirmation, app-specific coverage beyond the tested frameworks and optional grammar/translation review. The low-overhead everyday assistant and stronger troubleshooting tier follow dictation.

### Optional transcript review panel — qualified private workflow, rollout pending

`dictation-panel.py` provides a native GTK4 original/proposed-text view with Grammar, Translate and Translate + improve grammar modes, plus English/French/Spanish/German/Japanese output choices. The two-stage mode shows its intermediate translation and retains it with a warning if grammar review is unavailable. Focus the original field and hold F5 as usual. Review sends only the explicit text to the existing local everyday worker, with no tools, proxy or redirects. It preserves the original on unavailable/cooling/model errors and discards a proposal if its source changes. Copy is deliberate; no text is replaced in another app. Speech recognition remains English-only; translation is post-utterance text review.

Twenty-eight contracts and private native UI wiring checks pass. The actual public-file ASR → GTK4 field → French translation → grammar → private clipboard workflow also passed its functional checks, with semantic translation errors retained below. The panel batch is not installed; the human F5 attempt failed (a microphone desktop function appeared rather than listening), and exact prompt/app details remain pending. Fix that path before promoting the panel. After qualification, `--activate` installs the launcher; `--panel` can refresh it without restarting already activated speech services. The panel neither starts another model nor opens the microphone itself.

Primary API references: [IBus text commit](https://ibus.github.io/docs/ibus-1.5/IBusEngine.html), [AT-SPI accessible role/state APIs](https://docs.gtk.org/atspi2/class.Accessible.html). Metadata availability is tested locally; API documentation alone does not establish app support.

### Live F5 diagnosis and pending review qualification

The worker now logs only recognition of F5 and a generic pre-capture field refusal, with no typed/spoken content. A five-second parent allowance covers the helper’s four-second reply limit; accessibility RPCs and Begin have their own bounded deadlines. Twenty-three contracts pass. Native GTK/Qt/Wayland and browser checks cover this revision. The owner’s reported microphone-function popup remains a failed live attempt pending exact app/prompt detail; service readiness alone is not an acceptance pass.

`review-smoke.py --output /a/private/receipt.json --restore-default` qualifies six synthetic review cases using the existing supervised default model. It waits for three quiet samples and full model admission, preserves other profiles/locks, pins actual runtime/model bytes and metadata, and skips every completed response, including failed checks. Infrastructure interruptions remain separate and require inspection. No audio or owner app window is opened. Limited term/reference checks require independent meaning review; they are not general translation accuracy. That queue is complete; do not repeat it to improve the score. `review-language-smoke.py` records the separate three-language cohort.

### Input-bus reconnect recovery

The bridge now recovers from clean disconnects, and speech startup uses `Wants`/`After` so bridge recovery preserves the speech worker. Both follow the graphical session; logout wiring is checked, but logout itself was not tested. Removing a dynamic component can clear a static global engine in [IBus's implementation](https://github.com/ibus/ibus/blob/main/bus/ibusimpl.c). Startup therefore restores the configured native method **only when no engine is selected**; Begin has the same native-source fallback. A nonempty owner selection is preserved. XKB restoration uses Pantheon's pass-through engine and leaves the physical keymap alone.

Twenty-four contracts, a private actual GTK reconnect/insertion check, and actual installed-unit clean-TERM recovery pass. Recovery took3.46s with speech process and native source preserved. Manual stop remained stopped beyond the restart delay, supporting rollback. Earlier Requires reload, empty-engine and stale private socket failures remain in receipts. No owner IBus restart, microphone capture or owner window change was used. These tests do not turn the failed human F5 attempt into a pass; a retry is pending.

Idle ASR currently retains its model and checks resource limits before loading/recording and during capture. Idle memory-pressure reclamation is still open; the optional local review queue waits for sufficient headroom and does not evict owner jobs.

### On-demand model candidate — private native qualification complete

New source keeps the F5 listener ready without loading the native SDK/model. Explicit start binds the original field, loads only with another1GiB above the6GiB desktop reserve, then rechecks that field before microphone capture. Release/Escape during preparation prevents capture. A single exclusive model lease covers load/capture/flush; idle cleanup cannot free an active model. Short utterances reuse it for60s; idle or memory pressure releases it, and the listener stays available. The idle loop samples every5s while resident/waiting. Missing headroom produces a waiting state that clears when admission recovers. There is no new worker or model download.

Forty-six contracts cover release during load/Begin, focus loss, admission/recovery, overlap, warm reuse and close. Private actual Qt6, accessibility-enabled Brave and headless GTK4 Wayland checks pass the new no-insertion `Check` RPC and reject changed focus. One distinct CPU file-to-GTK4 lifecycle fixture passes; it does not replace prior accuracy results. Native RSS was37.59MiB before SDK import,918.73MiB after speech,134.59MiB after close (784.14MiB reclaimed). A reload without further inference closed successfully, ending187.86MiB. Retained library/allocator memory remains; repeated-cycle growth and long-run stability are not qualified.

A separate no-inference native controller test automatically released the model at61.00s:888.25→121.17MiB RSS (767.08MiB reclaimed). Both tests preserved at least11.07GiB available, reported0RPM and stayed below40.0C. No microphone, physical keyboard, owner window or audio route was used. [Receipts and exact evaluated sources](../local-ai/receipts/dictation-lifecycle-2026-10-18/). RSS comparisons are within each process, not a cross-kernel speed ranking or acoustic measurement. The ASR fixture predates the final waiting-state/retry-guard additions; those are covered by unit checks, while native timeout and framework tests pin the later source. Completed model trials were not rerun.

**Deployment remains pending:** the installed owner speech service still uses its earlier eager model. The candidate was tested privately without replacing it during the pending human F5 retry. The reported microphone-function prompt is unresolved; these tests do not prove physical-key delivery or human speech. The optional panel remains uninstalled. Source publication is not promotion to universal hardware acceptance.

### Review pilot result

The pinned everyday4B finished6 synthetic text-review cases: **5/6 limited checks**, all within reserve/thermal guards (1.99–3.43s warm request path, min9.48GiB available, max2516RPM/42.75C). The failed French literal translation changed `PWNED` to `PWNÉ`; it did not execute that instruction. A grammar case also left capitalization/punctuation unpolished. [Exact outputs and frozen source](../local-ai/receipts/dictation-review-2026-10-18/qualification-v1.json) preserve the failure. The separate [English/German/Japanese probes](../local-ai/receipts/dictation-review-2026-10-18/additional-languages-v1.json) passed3/3 limited checks (3.21–3.64s, min11.51GiB available, sensors reported0RPM, max40.30C). These are small functional probes, not general translation accuracy, acoustic measurements or kernel-diagnosis evidence.

The [actual private panel workflow](../local-ai/receipts/dictation-review-2026-10-18/panel-workflow-v1.json) used the existing public10.4s LibriSpeech clip:0% normalized WER, first widget text5.00s and complete ASR path12.80s including startup/streaming/flush. Translation and grammar requests took7.02s and7.09s. Original, intermediate and private clipboard checks passed; min11.04GiB available, reported0RPM and max40.17C. Meaning drift remains: “stew” became “soup” and “bruised potatoes” became “crushed potatoes”; the grammar stage returned that translation unchanged. Functional integration is qualified for this fixture, translation fidelity is not. No ambient microphone, physical key or owner app was used. Source/receipts are published through [PR86](https://github.com/techmore/ElementaryOS_MSeries/pull/86); human F5 acceptance and on-device rollout remain open.

The follow-up eight-cycle native **reload-only** soak held closed RSS around107.14–107.20MiB after the first cycle; the last four samples spanned48KiB. This is a bounded no-inference observation, not a repeated-recognition or indefinite always-on soak. A separate public-file pipe-start/close and silent-child cancellation test passed (cancel0.203s, no native SDK/inference). Current source also polls a stalled active pipe so release/resource guards stay live, covered by the46-contract suite. These changes and frozen-source differences are retained separately rather than repeating completed ASR quality trials.

## Apple Neural Engine engine (candidate) — 2026-10-18

`ane-dictate.py` runs Parakeet TDT 0.6B v3 (Core ML reference, encoder on the ANE via omarchy-ane, mel/decoder on Honeykrisp) over the whole utterance after F5 is released. It is a standalone service (`mseries-ane-dictate.service`, conflicts with the other F5 services; **not installed or enabled**) and is not wired into the lazy-controller panel. Offline: `python3 ane-dictate.py --wav FILE --repeat 5`.

Measured on this M1 Pro (pinned LibriSpeech clip, warm runs, private Mesa 26.2.4 ICD): 10.4 s of audio in 0.55-0.58 s (RTF 0.055, 5 runs after warm-up), versus 3.0 s median (RTF 0.29) for the current transcribe.cpp streaming path; a 41.7 s clip in 1.16 s. The text is word for word the same as the CPU Parakeet output on that clip. Cold first call 2.2 s (encoder emission is cached on disk; the very first ever run took 35-63 s).
Upstream `parakeet_dictation` is out of step with the installed mlx-omarchy 0.7.33 CLI (calls a removed `_verify_assets`, builds `AneIsland` without `seal_assets`); `ane-worker-shim.py` restores the CLI's asset sealing without editing the wheel. Fixes in the client: runs of dots and a stray non-Latin token on trailing silence are removed, and audio over ~29 s is cut at the quietest 100 ms so the model's fixed 30 s chunking never splits a word (without it, one of four repeats of a 41.7 s clip garbled a word at the boundary; with it, all four were intact). `test_ane_dictate.py`: 6 tests.
**Not verified:** one clip only (not a WER set); any live F5 session; the built-in microphone blocker (see the handoff) is unchanged, so spoken input through this path is untested; panel integration; a hung ANE submission needs a reboot per upstream.

### ANE engine inside the F5 controller — 2026-10-18

`STREAM_ENGINE=ane` makes `stream-dictate.py` (the lazy-model controller, with its resource guard, idle release, IBus/ydotool output and cancel handling) use `dictation_ane.AneModel` instead of transcribe.cpp: audio is collected while F5 is held and transcribed on release (`run_ane`), so there is no live partial text in this mode. The ANE worker starts on first F5 and is closed by the idle trim like the other model. Default stays `stream`; enable with `systemctl --user edit mseries-stream-dictate` and `Environment=STREAM_ENGINE=ane` (not done on the owner's service).
Verified offline through the real controller (`STREAM_TEST_WAV` clip played at real time, dry output): the full 162-character sentence arrived as one commit about 1.8 s after the audio ended on the first (cold) call. `STREAM_ENGINE` unset: 12 lifecycle/contract tests unchanged and passing. Not verified: live microphone, IBus insertion in apps, idle release of the worker.

### Press-once mode — 2026-10-18

`STREAM_MODE=toggle` (default `hold`): press F5 once to start (chime, "Listening…"), press again to finish; Escape cancels; key repeat and release are ignored. Combine with `STREAM_ENGINE=ane` through a systemd drop-in (`Environment=STREAM_ENGINE=ane` and `Environment=STREAM_MODE=toggle`). Not done: a mic cursor. Pantheon/Gala has no API for changing the pointer over another app's text field; feedback is the start/stop chimes, the notification and the panel status.

### Rolling ANE streaming — 2026-10-18

With `STREAM_ENGINE=ane` the controller no longer waits for the second F5: every `STREAM_ANE_INTERVAL` (0.6 s) of new audio the whole segment is re-decoded on the ANE (about 0.05 x real time) and the words two consecutive passes agree on, minus the newest one, are typed (append-only; the tail is typed after the final pass on release, 0.6 s measured on 10 s and 41 s clips). Segments longer than 16 s are closed at the quietest 100 ms of the last 5 s and the overlap with the next segment is trimmed.
Offline through the real controller (clip played at real time): a 10.4 s sentence appeared as 10 chunks of 1-6 words about every 0.6 s, the first about 4 s after start including the one-time worker warm-up. A 41.7 s clip with no pauses (the same sentence four times back to back) came out with 2 small errors at forced mid-word cuts; real speech with pauses is expected to do better, unmeasured. Not verified: live mic, how many words you perceive per second, CPU/thermal cost of repeated passes.

### Latency tuning and typing-interrupt — 2026-10-18

Typing any non-modifier key while dictating (ANE engine) ends dictation at once and drops words not yet typed, so nothing lands in the middle of your sentence (Escape still cancels). Latency was measured offline on the pinned 10.4 s clip with `STREAM_ANE_TRACE=1`: lag = audio time when a word was typed minus the earliest audio prefix whose decode contained it. Every pass costs about 0.5 s whatever the length (the encoder window is a fixed 30 s), so the submit interval does not matter below that (0.3, 0.4 and 0.6 s all gave a 2.0 s median lag with 1 held-back word). Typing from a single pass (`STREAM_ANE_AGREE=1`) gives median lag 0.6-1.3 s but typed hallucinated words from truncated audio ("Well, I'm World War"), so two agreeing passes stay. Holding back no extra word (`STREAM_ANE_HOLD=0`, now the default) gives a 1.5 s median (3 runs, p90 about 2.9 s, includes the cold start of the first words). Idle release of the ANE worker is 180 s instead of 60 s. A fourth back-to-back test run was refused by the resource guard, as designed.
