# F5 dictation (local speech to text)

Hold **F5** (the microphone key), speak, release: the text is typed into the focused field of any app.
Voxtype 1.1.1 (MIT) + whisper.cpp `base.en` on the CPU, ydotool for typing (same stack as Omarchy).
Audio stays on the Mac; nothing is stored. Install: `bash mseries/install-dictation.sh` (`--uninstall` to remove).

Pieces
- `91-mseries-dictation.hwdb`: F5 becomes KEY_F20 (hid-apple otherwise makes it backlight-down). Supersedes the opt-in F5 remap in `90-mseries-keyboard.hwdb`.
- `aop-mic.sh` + `mseries-aop-mic.service`: the built-in mic (AOP, ALSA `hw:1,0`) is raw 3-channel 32-bit with DC offset and no profile; PipeWire only offers the silent headset jack. The bridge publishes it as source `mseries-builtin-mic` (never auto-linked to speakers). Voxtype binds to it with `PIPEWIRE_NODE`.
- `config.toml`: hold-to-talk, `eager_processing` (4 s chunks transcribed while you talk). Copied once to `~/.config/voxtype/`.
- `STT-RESEARCH.md`: engine survey (Parakeet, Moonshine, MLX on Linux) and the staged upgrade plan.

Known gaps (2026-10-18)
- The live F5 round trip with a person speaking is **not yet verified**. Verified: key mapped to F20, service listening, bridge to Whisper end to end (a hiss recording transcribed as "Pshhh."), and offline speech through the same filter transcribed correctly.
- The bridge captures continuously, which costs power (AOP is already a battery suspect); make it start only while recording.
- Mic gain (`AOP_MIC_GAIN`, 0.2) is untuned and the mic is hissy; typing assumes a US layout (ydotool).
- Grammar clean-up by a local LLM is a stub in `config.toml` (`[output.post_process]`), not tested.
