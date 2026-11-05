# Getting started with DialogueFoundry

Use Windows x64 and Python 3.10–3.13 with Tkinter. The source targets Python 3.10;
the optional Kokoro package explicitly excludes 3.14 and newer. Other interpreter
and OS combinations are not a tested desktop support promise.

Clone and install the base app using the commands in the [README](../README.md).
An installed Python must include Tcl/Tk; the embeddable Python ZIP alone is not
the recommended development setup. `python -c "import tkinter"` should succeed.
FFmpeg **and FFprobe** must resolve on `PATH` for validated exports. This project
does not automatically install media tools. Close and reopen PowerShell after
changing `PATH`, then check both `-version` commands.

## Optional local voices

Run these commands from the repository root, choosing one or both providers:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-piper.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-kokoro.txt
.\.venv\Scripts\python.exe app.py
```

In **Model library**, review the model's license information, select a model and
explicitly download it. Installation checks expected sizes and SHA-256 hashes;
the runtime verifies required assets before inference. Downloading a model is
separate from installing its Python runtime. All Kokoro English voices share the
`kokoro-82m-v1` installation. Piper models are installed separately.

For a first local export, install Kokoro and its model, then run:

```powershell
.\.venv\Scripts\python.exe main.py --input examples/hello.conversation.json --provider kokoro --voice-map examples/hello.kokoro-voices.json --output hello-local.wav
```

This can synthesize without internet after prerequisites are installed. No model
download or fallback to Edge occurs automatically. The default model folder is
`%LOCALAPPDATA%\Windows TTS App\models`; keep that existing identity when upgrading.
Choose a writable output directory and a new filename. Play the result and check
the final half-second pause. Preview/playback controls use Windows audio.

Use `.wav`, `.mp3` or `.m4a` as the explicit CLI output extension. The desktop
offers format, sample rate, channel and normalization controls. Existing outputs
are preserved unless replacement is selected. Installing package requirements
with version ranges does not recreate an exact release environment; see
[Release process](RELEASE_PROCESS.md).

If installation, model loading or export fails, use
[Troubleshooting](TROUBLESHOOTING.md). Before sharing scripts, projects, audio or
diagnostics, read [Privacy](PRIVACY.md) and [Licensing](LICENSING.md).
