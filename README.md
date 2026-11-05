# DialogueFoundry

**Turn scripts into multi-voice audio on Windows.**

DialogueFoundry turns written conversations into ordered speech with distinct
voices, pauses and optional scene effects. Use it for fictional interviews,
language lessons, narrated scripts and dialogue prototypes. Choose local CPU
voices with Piper or Kokoro, or the online Microsoft Edge TTS service.

This is a **preview preparation**, not a stable release announcement. The source
reports version **1.0.0**; that number does not establish release readiness.
No downloadable package is advertised here. Some model terms and third-party
distribution requirements remain unresolved; see
[Licensing](documentation/LICENSING.md) and
[Known limitations](documentation/KNOWN_LIMITATIONS.md).

## What it can do

- Read `Speaker: text` scripts or structured JSON with stable speaker IDs.
- Map speakers to voices, preserve ordered turns and explicit pauses, and save
  structured projects and reusable role mappings.
- Preview local voices, replay or stop playback, report progress and cancel work.
- Export validated WAV, MP3 and M4A with optional normalization and audio settings.
- Manage explicit, checksum-verified model downloads in the desktop Model library.
- Review folder batches in Audio Director, audition exchanges and apply scoped
  telephone effects. Manual operation needs no planning service. Optional AI
  planning requires a separately configured local or cloud endpoint.
- Use Audio Director CLI direction files for mixed-provider casts.

## Providers

| Provider | Connectivity | Runtime installation | Model downloads | Limits |
| --- | --- | --- | --- | --- |
| Microsoft Edge TTS | Internet for synthesis | Base `requirements.txt` | No local weights | External service; availability and terms can change. No user API key in this TTS path. Explicit speed control is unsupported by this app. |
| Piper | Local synthesis after setup | `requirements-piper.txt` | Select each model in Model library | CPU; model quality and license vary; includes voices with restrictive or unclear terms. |
| Kokoro-82M | Local synthesis after setup | `requirements-kokoro.txt`, Python 3.10–3.13 | Shared model and voice-style assets | CPU; pinned English catalog; phonemization includes GPL components. |

Local installation and downloads require network access. Edge use and cloud
planning send data off the machine; cloud planning can require credentials and
paid service access. See [Privacy](documentation/PRIVACY.md).

## Windows quick start

Use Windows x64, Python **3.10–3.13** with Tkinter, Git, and FFmpeg with FFprobe
available on `PATH`. Python 3.13 is a suitable shared environment for the optional
providers. Install media tools from a source you trust; check their licensing
before redistributing them. Verify in a new PowerShell window:

```powershell
git clone https://github.com/kifayathusain/speech-to-text-windows-app.git
cd speech-to-text-windows-app
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import tkinter; print('Tkinter available')"
ffmpeg -version
ffprobe -version
.\.venv\Scripts\python.exe app.py
```

The product name is DialogueFoundry. Existing windows and user storage still use
**Windows TTS App**, and locally built executables are **WindowsTTSApp.exe**.
The Python package remains `ttsapp`.

## First export from a tracked sample

With internet access and media tools installed, run from the repository root:

```powershell
.\.venv\Scripts\python.exe main.py --input examples/hello.txt --provider edge --output hello.wav
```

The sample uses the configured `Receptionist` and `Caller` labels. Choose an
unused output name, or explicitly add `--overwrite` to replace it. This command
performs real online synthesis when you run it. For an offline first export,
install a local runtime and its model first; follow
[Getting started](documentation/GETTING_STARTED.md).

## Desktop and CLI

Run `app.py` for the desktop. Choose your provider, configure voices, preview,
then generate. The structured JSON editor supports more than the legacy two
speaker controls. **Audio Director…** opens folder planning and batch rendering.

```powershell
.\.venv\Scripts\python.exe main.py --help
.\.venv\Scripts\python.exe main.py --input examples/hello.conversation.json --provider edge --voice-map examples/hello.edge-voices.json --output dialogue.mp3
.\.venv\Scripts\python.exe main.py director --help
```

Running `main.py` without arguments retains a legacy `conversation.txt` default;
that personal input file is not supplied in a fresh clone. Use the explicit sample
command above. See [Usage and examples](documentation/USAGE.md) for mappings,
pauses and Director commands.

## Documentation

- [Getting started](documentation/GETTING_STARTED.md)
- [Providers and models](documentation/PROVIDERS_AND_MODELS.md)
- [Usage and examples](documentation/USAGE.md)
- [Privacy](documentation/PRIVACY.md)
- [Troubleshooting](documentation/TROUBLESHOOTING.md)
- [Architecture](documentation/ARCHITECTURE.md)
- [Release process](documentation/RELEASE_PROCESS.md)
- [Known limitations](documentation/KNOWN_LIMITATIONS.md)

Clean Windows installation acceptance and high-DPI desktop checks remain pending.
AI planning is experimental; review casts and effects and listen to outputs.
Catalog accent metadata does not guarantee a specific delivery or voice quality.

## Community and licensing

Read [Contributing](CONTRIBUTING.md), the [Code of Conduct](CODE_OF_CONDUCT.md),
[Support](SUPPORT.md), [Security](SECURITY.md) and [Changelog](CHANGELOG.md).
Private reporting contacts still need maintainer configuration.

DialogueFoundry is licensed under **GPL-3.0-or-later**.
Copyright (C) 2026 Kifayat Husain. See the complete [license](LICENSE) and
[copyright and scope notice](COPYRIGHT.md). Third-party licenses remain in force;
see [Licensing](documentation/LICENSING.md) and
[Third-party notices](THIRD_PARTY_NOTICES.md). Application licensing does not grant
unrestricted rights to voice models, external services or generated audio.
