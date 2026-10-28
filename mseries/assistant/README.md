# On-device assistant (LFM3-Audio-2B)

Tracking issue: [#649](https://github.com/techmore/ElementaryOS_MSeries/issues/649) (the spec is also in [ISSUE-SPEC.md](ISSUE-SPEC.md)).

## Keys

| Key | What it does |
|---|---|
| **F5** | Dictation, as on a Mac. Tap, talk, and tap again. The streaming Nemotron path, unchanged ([../dictation](../dictation/README.md)). |
| **F6** | Inline suggestion in the focused text field. **Tab** inserts it; Esc or any other key drops it. |
| **Ctrl+Alt+R** | Smart Reply chat draft ([../smart-reply](../smart-reply/README.md)). |

F6 refuses terminals, password managers, the lock screen, and password, card and one-time-code fields. It reads only the field's own text before the caret (at most 1,500 characters), which never leaves the machine.

## Install

```bash
bash mseries/assistant/install.sh
```

Add `--download-model` on a machine that lacks `~/.cache/mseries-metal2vk/lfm3-audio-2b-8bit` (2.5 GB). `--uninstall` removes the service and F6 binding but keeps the model and venv.

The installer creates `~/.local/share/mseries-ai/lfm3-audio-venv`, an overlay venv that reuses the private Vulkan MLX from `~/.local/share/mlx-omarchy` through a `.pth` file. It adds mlx-vlm pinned to `efd4b9f` (LFM3-Audio support, which no release carries yet) and mlx-audio, both with `--no-deps` so a stock MLX never replaces the private build, plus requests, pillow and miniaudio. It then installs `mseries-assistd.service` and rebuilds `mseries-reply` with the F6 `suggest` command.

## Service

`mseries-assistd` serves one model on `127.0.0.1:8772`. It loads on the first request (about 3.4 s), unloads after 10 idle minutes, and refuses to load when free memory would fall below the 6 GiB desktop reserve plus 3 GiB.

```bash
curl -s localhost:8772/health
curl -s localhost:8772/v1/complete -d '{"prefix":"The meeting tomorrow has been moved to"}'
curl -s --data-binary @clip.wav localhost:8772/v1/audio/transcriptions
curl -s localhost:8772/v1/audio/speech -d '{"input":"Hello"}' -o hello.wav
curl -s localhost:8772/v1/chat/completions -d '{"messages":[{"role":"user","content":"Hi"}]}'
journalctl --user -u mseries-assistd -f
```

`/v1/assist/voice` takes a WAV and returns the spoken answer as text and base64 WAV, for the assistant app (milestone 2).

## Measured (M1 Pro, Oct 27, warm model)

| Job | Time |
|---|---|
| Suggestion (16 tokens) | 1.0–1.6 s |
| Speech-to-text, 10 s clip | 1.9 s, exact transcript |
| Text-to-speech, 3.5 s of audio | 5.4 s |
| One-line chat answer | 0.6 s |

`MLX_OMARCHY_BATCH_WORK=20000` (the PR #648 value) made suggestions 7% faster and speech-to-text 13% faster than the default.

## Model notes

- The chat template has no "thinking off" switch, so the service prefills an empty `<think></think>` block.
- Continuation works by prefilling the assistant turn with the typed text. Asking the model to "continue" makes it chat about the text instead.
