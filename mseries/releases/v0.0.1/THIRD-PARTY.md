# Source and external runtime notices

Repository source is distributed under the included GNU GPL version 3 license.
The exact repository commit and every packaged source digest are in manifest.json.

The existing external dependencies retain their own licenses; this archive does
not redistribute model weights or native binaries:

- [transcribe.cpp 0.4.0](https://github.com/handy-computer/transcribe.cpp/tree/v0.4.0): MIT. The qualified native library SHA256 is pinned in the manifest and checked before update.
- [NumPy](https://numpy.org/doc/stable/license.html): BSD license; existing qualified version 2.5.4.
- [Nemotron English streaming](https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b): NVIDIA Open Model License.
- [Pinned GGUF conversion and notices](https://huggingface.co/handy-computer/nemotron-speech-streaming-en-0.6b-gguf/tree/7df420cc3fb915a3b334560dac712af44fc41ef5): model license and NOTICE accompany the upstream artifact. The installer downloads it only when explicitly requested.
- GTK, GLib/GIO, AT-SPI, IBus, Python and ffmpeg are existing system dependencies.

Synthetic qualification audio is public LibriSpeech (CC BY 4.0,
Panayotov/Chen/Povey/Khudanpur, https://www.openslr.org/12). No audio is in this
release archive. No private journal, transcript, model memory, task or account
settings are distributed.
