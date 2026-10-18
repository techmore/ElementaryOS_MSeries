# v0.0.1 — English F5 speech to text

**Release candidate: physical F5 in the currently running ChatGPT app failed.**
The key reaches the speech service; the input guard refuses before microphone
capture because the app does not expose its editable field. The staged launcher
compatibility fix needs a full owner-controlled ChatGPT relaunch and a new human
check. A working public release is not declared until that gate passes.

This is a small desktop update for an **already configured elementary OS M-Series
M1 Pro j314s with 32 GB RAM**, Python 3.14, the existing pinned CPU speech runtime,
IBus bridge and F5 remap. It is not a fresh-install ISO. The check below refuses
unsupported or incomplete installations before changing files.

The package contains source code. No model, native binary, recording, private
settings, kernel, voice conversation or troubleshooting agent is bundled.
English words are inserted as the recognizer commits them. No language model,
grammar rewrite, clipboard or translation is used by the release transcript UI.

## Verify and install

Download the `.tar.gz`, `provenance.json` and `SHA256SUMS` from the same GitHub
release. Verify their checksums before extracting:

```sh
sha256sum -c SHA256SUMS
tar -xzf elementaryos-mseries-f5-0.0.1.tar.gz
cd elementaryos-mseries-f5-0.0.1
./install.sh --check
```

The package's complete file manifest is verified before host inspection or
installation. It is an integrity check; obtain the files from the trusted
repository release. Do not run the installer with sudo.

Reuse the verified model already installed, or provide its local path:

```sh
./install.sh --install --model-source /path/to/nemotron-speech-streaming-en-0.6b-Q8_0.gguf
```

If the pinned model is absent, this explicit alternative downloads it from its
pinned Hugging Face revision and checks SHA256. Review the model license first:

```sh
./install.sh --install --download-model
```

The model filename is case-sensitive: uppercase `Q8_0`. Model, runtime and source
pins are in `manifest.json`. The installer uses a private, versioned rollback
checkpoint and preserves the existing hold/toggle preference and native input
selection. Only owned speech/input services reload. It does not restart apps,
IBus, the menu bar or the audio stack. An already active version checkpoint must
be rolled back before reapplying; later owner edits cause a safe refusal.

## Use F5

Focus a normal editable field. In toggle mode, press F5, wait for Listening,
speak English, then press F5 again. In hold mode, hold F5 until Listening and
release to finish. Escape cancels; typing ends dictation. The installer preserves
the mode already chosen on your desktop.

Open **Dictation** for an English transcript field. The release UI contains no
grammar or voice-reply controls. Password, unknown, inactive and inaccessible
fields are refused before microphone capture. Stable words stream; speculative
draft composition is suppressed because Chromium could commit it on focus loss.

For ChatGPT's Electron app, prepare its user launcher:

```sh
./install.sh --enable-chatgpt
```

This preserves the desktop entry's other fields and URLs, enables renderer
accessibility and selects the IBus environment. It does not alter the running
app. Fully quit ChatGPT and reopen it from Applications when convenient; closing
one window or launching a second instance may leave the old process running.
A later retry also failed while the original process was still running without
the new flags/environment. The fix has not activated. The current ChatGPT
configuration remains an unresolved release gate above.

## Rollback

```sh
./install.sh --rollback
```

This restores the immediate pre-v0.0.1 payload, launcher and engine when their
tracked files still match. Private backups and previous models remain. An
independent ChatGPT launcher override has its own rollback:

```sh
python3 -B mseries/dictation/enable-app-input.py --app chatgpt --rollback
```

## Qualification and limits

The retained CPU/public-file results include two resident 62.61-second trials,
finishing 0.048/0.062 seconds after audio. Installed routes passed GTK4 public-file
ASR; GTK3/Qt6/Brave fixtures; and Code/Newelle/Tasks lease/cancel fixtures, with
positive real-app ASR in separate pinned cohorts. These are not seven new ASR
benchmarks. Three initial fixture argument failures and the sustained CPU
sensor-summary failure remain recorded; completed tests were not rerun to hide
them. Installed samples retained at least 10.48 GiB available at no more than
2530 RPM / 49.01°C. RPM is a noise proxy, not acoustic measurement.

Speech preserves a six-GiB desktop reserve and stops at 2700 RPM / 63°C.
Native ANE and MLX research, high-capability diagnosis, broader app coverage,
natural voice, factory boot and power/battery qualification remain separate.
The permanent six-hour developer watcher continues discovering candidates;
release pins change only after new, separately identified qualification.

Read the [canonical qualification ledger](https://github.com/techmore/ElementaryOS_MSeries/blob/main/mseries/dictation/QUALIFICATION-INDEX.md)
and [public results](https://techmore.github.io/ElementaryOS_MSeries/local-ai.html#english-f5)
before any continuation. Preserve successful and failed evidence. New popular
models and codebases are candidates, not automatic release upgrades.
