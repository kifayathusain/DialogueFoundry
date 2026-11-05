# Contributing to DialogueFoundry

DialogueFoundry's application source and original project material are licensed
under [GPL-3.0-or-later](LICENSE); see the [copyright notice](COPYRIGHT.md) and
[Licensing](documentation/LICENSING.md). Contributions to that material must be
offered under the same license, with rights to contribute confirmed and all
third-party provenance/notices preserved. Contributors retain copyright in their
contributions; no copyright transfer or separate contribution agreement is required
by this policy. Third-party materials retain their own terms.

## Development setup

Use Windows x64, Python 3.10–3.13 with Tkinter and Git. The source compatibility
floor is 3.10; the optional Kokoro dependency requires `<3.14`. Python 3.13 is the
shared development target used in the current audit.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
# Optional local provider runtimes; models are installed separately:
.\.venv\Scripts\python.exe -m pip install -r requirements-piper.txt -r requirements-kokoro.txt
```

See [Getting started](documentation/GETTING_STARTED.md) for FFmpeg, models and
the first export. Build dependencies are in `requirements-build.txt`; those
requirements are not a release lock.

## Conventions

Use readable PEP 8 Python, four spaces, descriptive names, explicit control flow,
type hints and useful public API docstrings. Prefer 88 columns. Keep functions
focused and handle errors and cleanup explicitly. Do not suppress lint rules to
hide problems or reformat unrelated code.

Keep UI callbacks separate from business rules, use queued worker events, preserve
provider interfaces and keep models, phonemization and FFmpeg operations in their
own modules. See [Architecture](documentation/ARCHITECTURE.md). Avoid unrelated
refactoring and new frameworks without a concrete need.

## Checks

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

Use `ruff format` only on intended changed Python files. Add observable behavior
tests for changed behavior, including relevant errors, cancellation and resource
cleanup. Mock services/model inference for unit tests. Report existing failures
separately; do not claim unavailable checks passed.

Structured regression fixtures and the format schema are included under
`examples/structured/`; no private development documents are required.

The suite imports Tkinter, and several tests construct actual windows and require
a Windows interactive desktop/Tcl/Tk. Windows playback is opt-in using
`TTS_PLAYBACK_TESTS=1`. Tests marked `integration` and `real_model` describe
requirements; the marks alone do not skip tests. Real media checks use
`TTS_FFMPEG_TESTS=1` and `TTS_EXPORT_TESTS=1` with both tools on `PATH`.
Real inference checks require the corresponding `TTS_PIPER_MODEL_DIR`,
`TTS_KOKORO_MODEL_DIR`, `TTS_LONGFORM_MODEL_DIR`, `TTS_GUI_PIPER_MODEL_DIR` or
`TTS_M11_MODEL_ROOT`. Model download tests require network and explicit
`TTS_MODEL_DOWNLOAD_TESTS=1`; package acceptance uses `TTS_PACKAGE_EXE` and can
download real models. Read the relevant test's gate before enabling it. No live
model download, network synthesis or listening review is needed for documentation
edits. Synthetic media tests may still require actual FFmpeg.

## Pull requests

Describe the user-visible problem, scope, validation and limitations. Include a
fictional minimal reproduction, tests for changed behavior and matching public
documentation. Identify dependencies, copied code and model/asset terms. Remove
private text, credentials and local paths from logs. Do not include generated
audio, model weights, environments or personal development records. For proposed
API, parser or file-format changes, explain backward compatibility. Follow the
[Code of Conduct](CODE_OF_CONDUCT.md), [Support](SUPPORT.md) and
[Security](SECURITY.md) policies; do not disclose vulnerabilities in public PRs.
