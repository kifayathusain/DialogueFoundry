# Windows TTS App

Generates conversations from plain-text scripts or structured JSON with editable
role-to-voice mappings and exact segment after-pauses. Choose Microsoft Edge TTS
or installed CPU-only Piper/Kokoro voices, then export WAV, MP3 or M4A with FFmpeg. The desktop application is named **Windows TTS App**; its
version is shown in the window title and is maintained as `APP_VERSION` in
`ttsapp/config.py`.

## Prerequisites

- Python 3.10–3.13 for all providers (3.13 recommended). Edge/Piper also tested on 3.14.
- [FFmpeg and FFprobe](https://ffmpeg.org/) installed and available on `PATH`
  for source runs and packages without bundled tools.
- Internet for Edge TTS and initial model downloads. Installed local voices run
  offline on CPU; no API key or GPU is required.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# optional, for running tests:
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Usage

### Desktop app (Windows)

```powershell
.\.venv\Scripts\python.exe app.py
```

Use **Plain text** for the familiar `Speaker: text` editor and configured
Receptionist/Caller defaults. Choose one provider per job. **Open / Import** uses
the extension to open plain text or validated JSON; invalid JSON never falls back
to text. **JSON** shows every declared role, ordered segments and preflight
diagnostics. Select a role or segment, edit its fields, then use **Apply role** or
**Apply segment**. Unsupported explicit settings block generation.

**JSON Save As** exports source dialogue/settings/extensions. **Save project As**
also preserves active voice mappings, provider/locale and processing/export
settings. **Open project** restores its embedded snapshot even if the original
source moved. **Apply preset** explicitly enables exact role/provider/locale
preferences for automatic roles while preserving manual/project selections.
Directions are visible notes; they do not enforce emotion or style. Edge does not
support explicit speed. Repeated voice IDs produce shared-voice warnings.

Preview uses selected-role dialogue and effective supported speed, with an explicit
**speech only** label. Generate, Cancel, Play/Replay, Stop, model-library access,
output browsing and overwrite confirmation remain available. **Advanced export
options** exposes codec, bitrate, sample rate, channels and normalization. The
editing surface scrolls at small sizes and keyboard focus reveals off-screen
fields. See the [structured desktop guide](docs/setup/STRUCTURED_DESKTOP.md).

The default desktop output is
`%USERPROFILE%\Documents\Windows TTS App\conversation.mp3`; isolated job
parts are retained in adjacent `audio_parts`. Existing final audio is published
atomically only after successful validation. Model verification, import, synthesis
and FFmpeg work use background workers; no import automatically downloads models
or previews voices. Tkinter remains the desktop framework.

Current acceptance: M13/M14 pass the approved offline/fake-provider gates.
M15–M17 remain blocked on required 150%/200% Windows OS scaling evidence; the
tested development display reports 100%. M10's separate clean-machine blocker
is unchanged. See the [tracker](docs/milestones/MILESTONE_TRACKER.md).

### Build a distributable Windows app

Use Python 3.10–3.13 with Tkinter for the full CPU package:

```powershell
python -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build-windows.ps1 -PythonExecutable .\.build-venv\Scripts\python.exe
```

Each build creates a fresh `dist/release-*` directory and portable ZIP, preserving
previous builds. Extract the complete folder and launch `WindowsTTSApp.exe`.
The full profile includes Kokoro, Piper and Edge runtimes; model weights remain
separate downloads. Optional `-FFmpegDirectory` bundles explicitly supplied,
license-documented FFmpeg and FFprobe tools with integrity hashes; otherwise both
must be installed on PATH. See [Windows package setup](docs/setup/WINDOWS_PACKAGE.md)
for build profiles, diagnostics, licensing status and the required clean Windows
11 completion check. No release is published automatically.

### Troubleshooting

- **"FFmpeg is required" / FFmpeg not found:** Install FFmpeg, add the folder
  containing `ffmpeg.exe` to the Windows `PATH`, restart the app, and verify
  from PowerShell with `ffmpeg -version`.
- **Speech generation failed:** Confirm internet access and try again. If
  you changed a voice, verify its Edge TTS voice name; the underlying service
  error is shown in the dialog.
- **Cannot save the output:** Use "Browse..." to choose a folder where your
  Windows account has write access, such as Documents.
- **FFmpeg could not combine the audio:** Check the FFmpeg installation and
  available disk space. The dialog includes FFmpeg's error details; the
  existing final audio is preserved when combination fails.

### Command line

1. Edit `conversation.txt` with lines formatted as `Speaker: text`, one line
   of dialogue per line of the file. Blank lines are ignored.
2. Each `Speaker` label must have a configured voice in
   `ttsapp/config.py` (`VOICES`). The defaults are `Receptionist` and
   `Caller`.
3. Run the app:

   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```

   This generates one MP3 per line in `audio_parts/` and combines them into
   `conversation.mp3` in the repository root.

Additive JSON CLI usage:

```powershell
python main.py --input docs/tts-sample.json --input-format json --provider edge --output dialogue.wav
python main.py --input dialogue.json --voice-map voices.json --output dialogue.m4a --overwrite
```

Mappings, speed validation, exact after-pauses and exports use the same service as
the desktop. New explicit CLI exports refuse replacement without `--overwrite`.
See [projects, presets and CLI contracts](docs/PROJECTS_AND_CLI.md). The commands
above perform synthesis when a user runs them; acceptance for this follow-up used
only injected fake providers and synthetic non-speech media.

If generation is interrupted after the per-line audio files already exist,
you can re-run just the combination step:

```powershell
.\.venv\Scripts\python.exe gen_audio.py
```

## Architecture

The CLI and Tkinter views share `ttsapp/service.py`. Legacy text uses
`parser.py`; structured input uses `conversation_document.py` and the pure
`speaker_mapping.py` resolver. Processed generation in `generation.py` retains
source spans, effective per-segment speed and ordered speech/silence metadata.
Provider implementations remain behind their common interface, with verified
model lifecycle separate from audio processing and UI state. `audio_export.py`
owns validated codecs/layout preparation and atomic publication.
`project_storage.py` handles bounded data-only snapshots and presets.
See the [current architecture](docs/architecture/ARCHITECTURE.md).

## Audio exports

The desktop supports validated WAV, MP3, and M4A with bitrate, sample-rate,
mono/stereo, optional loudness normalization, cancellation, and explicit output
replacement. Both FFmpeg and FFprobe must be on PATH for validated exports.
See [export setup](docs/setup/AUDIO_EXPORTS.md).

## Model library

Open **Model library...** to download, verify, cancel, reinstall, or remove
supported offline model files. Runtime and license details appear with each
model; Python inference dependencies are installed separately. See
[model library setup](docs/setup/MODEL_LIBRARY.md) for storage and recovery.

## Provider architecture

Generation now resolves a provider through `ttsapp/providers/registry.py`.
Microsoft Edge TTS remains the default, with the original CLI and desktop
behavior. The typed provider contract and cancellation boundaries are documented
in [the provider contract](docs/architecture/PROVIDER_CONTRACT.md).
Local model runtimes are optional and are not imported by default Edge routing.
The optional [Piper CPU provider](docs/setup/PIPER.md) is available through the desktop, JSON CLI and
Python API with explicitly verified local voices. The [Kokoro-82M CPU provider](docs/setup/KOKORO.md) is available on Python
3.10–3.13. The desktop now includes provider selection, local voice previews, replay/stop,
progress, and cancellation; see [desktop controls](docs/setup/DESKTOP_PREVIEW.md). See the
[tracker](docs/milestones/MILESTONE_TRACKER.md) for validated status.

[M11](docs/milestones/M11_ENGLISH_VOICES.md) adds the complete pinned British and
American English inventory: 28 Kokoro voices and 2,006 Piper speaker/quality
choices across 38 model variants. Search voices by name, quality or speaker and
filter en-US/en-GB in the desktop. Install selected Piper models through
[Model library](docs/setup/MODEL_LIBRARY.md); all Kokoro voices share one model
installation. Downloads remain explicit, with verified assets and per-model
license information.

## Tests

Contributors and Codex sessions must start with [AGENTS.md](AGENTS.md) and follow
the authoritative [coding standards](docs/CODING_STANDARDS.md). Development
tools are installed from `requirements-dev.txt`; Ruff and pytest are configured
in `pyproject.toml`. See the [milestone plan](docs/milestones/MASTER_PLAN.md) and
[tracker](docs/milestones/MILESTONE_TRACKER.md) for scope and completion gates.

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

The automated suite covers parsing, long Unicode input, multiple voices and
segments, output-path creation, reruns/overwrites, TTS and FFmpeg failures,
cancellation cleanup, and the desktop UI's background-worker/queue boundary.
Tests mock the Edge TTS and FFmpeg adapters, so they run offline and without
requiring the `ffmpeg` executable.

For package acceptance, follow the extracted-executable and clean-machine
checks in [Windows package setup](docs/setup/WINDOWS_PACKAGE.md). An isolated
folder on the development host is useful validation but does not establish a
clean Windows 11 installation. The [tracker](docs/milestones/MILESTONE_TRACKER.md)
records which completion gates have actually passed.
