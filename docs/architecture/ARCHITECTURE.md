# Current Incremental Architecture

## Audio Director follow-up

`gui.py` opens `director_gui.AudioDirectorWindow`, a worker/event-based workspace
with an independent ProviderManager lifetime and the existing model library and
Windows player. `director.py` owns immutable batch/file snapshots, bounded stable
folder discovery, source fingerprints, explicit cast linking, manual corrections,
timing resolution, scene scopes and whole-batch destination preflight.
`director_planner.py` owns the configurable OpenAI-compatible JSON-mode adapter,
metadata-first inventory, explicit cloud consent, data-only version-one response
validation and retained manual/document precedence. It has no filesystem or tool
operations in its plan contract. Presets/reports use existing bounded atomic JSON
storage. Original conversation words and speaker order remain authoritative.

`director_runner.py` provides widget-free per-file execution, failure policy,
cancellation, selected retries and multi-turn auditions. It delegates to
`service.generate_conversation` and the existing processed-generation/export
pipeline. Optional typed `segment_treatments` are validated before side effects,
included in request metadata/hash, and applied to speech PCM through
`audio_effects.py` before combining. Providers contain no FFmpeg/scene logic.
Scripted silence bypasses effects; deterministic natural gaps apply only to
omitted nonfinal inter-speaker pauses in the immutable source snapshot. All final
outputs retain existing validated atomic publication and cancellation behavior.
Private intermediate jobs are cleaned per Director file; reports omit dialogue,
prompts, credentials and raw model/provider responses. See the
[user guide](../setup/AUDIO_DIRECTOR.md) and
[acceptance evidence](../milestones/M18_M21_AUDIO_DIRECTOR.md).

For the original pre-migration snapshot see [CURRENT_STATE.md](CURRENT_STATE.md).
The existing `ttsapp` package and Tkinter framework are retained.

```text
main.py / app.py -> gui.py -> service.py -> provider contract / registry
                              |               | Edge -> legacy tts_engine.py
                              |               | Piper -> optional CPU runtime
                              |               | Kokoro-82M -> optional CPU ONNX
                              |               v
                              |          atomic native audio_files.py
                              v
                       audio_combiner.py -> FFmpeg -> final media

gui.py -> model_library.py -> models.manager -> trusted models.catalog
                                       |             sizes, hashes, licenses
                                       v
                            user-owned verified model directories
```

The default registry contains Edge; explicit local provider instances are
injected through the service API. Unselected inference dependencies are not
imported. Catalog factories build provider descriptors using the same trusted
asset metadata as the downloader. Edge retains its atomic adapter and MP3
stream-copy path. Local engines share native WAV publication and cooperative
background-worker cleanup. FFmpeg remains separate from model inference.

Model management has no UI dependencies. The library UI sends operations to a
worker and receives typed queued progress/status events. Long-running synthesis, provider verification, preview and input import use
background workers; the main thread captures snapshots and renders queued events. User paths and licensing/runtime setup
are documented in [model library setup](../setup/MODEL_LIBRARY.md).


## M06 processed generation

`service.py` retains the default Edge path and routes offline/explicitly processed
requests through `generation.py`. `text_processing.py` preserves normalized source
spans and provider limits. Per-job directories isolate chunks; `generation.json`
records hashes/states without private source text. Shared PCM silence and FFmpeg
native decoding keep audio processing outside providers. Line progress remains
compatible and chunk progress is additive. See [setup](../setup/TEXT_PROCESSING.md).


## M07 desktop provider sessions and preview

`provider_manager.py` resolves verified installed models, reuses the selected
session, and releases unused engines. `desktop_options.py` validates immutable
worker settings outside widgets. `preview.py` synthesizes actual selected
voice/speed to an atomically published bounded PCM cache and owns native async
playback. The Tkinter class now captures controls and dispatches generation or
preview work; typed queued events render progress/results on the main thread.
Model management is modal and closes idle sessions from its worker before
modification. Graceful shutdown waits asynchronously for native cleanup.


## M08 validated export transactions

`audio_export.py` owns typed codec/rate/channel/normalization settings, lossless
common-layout preparation, final media validation, and explicit atomic output
commit. `audio_process.py` owns cancellable/timeout child lifecycles and FFprobe
JSON calls. Generic `workers.py` waits for blocking cleanup under repeated async
cancellation. The original FFmpeg adapter remains for compatibility; advanced
UI/API paths add validated WAV/MP3/M4A without moving export logic into providers.


## M09 measured CPU sessions

`providers/onnx_sessions.py` creates explicit CPU-only sessions with bounded
intra-operation threads and sequential execution. Local providers fully verify
assets on each runtime load, then reuse verified resident data. Kokoro retains
only catalog voice styles and closes the voice archive immediately after loading.
ProviderManager avoids redundant disk scans when returning the selected provider;
closing/switching or a model-library modification ends that lifetime. Explicit
Model library verification remains a full integrity check. No model quantization
or change to phonemization, speed, text chunking, or audio processing is applied.


## M10 package entry and media tools

`app.py` preserves normal Tkinter startup and adds an explicit diagnostics mode.
`runtime_paths.py` verifies hashes before adding bundled media tools to PATH;
source runs retain external tool discovery. Damaged tools receive recovery
guidance in the desktop and a nonzero JSON report in diagnostics. The diagnostics
use the same providers, model manager and validated exports as the application.
PyInstaller hooks retain native CPU/phonemizer data while excluding unselected
auxiliary weights. Builds use fresh output directories and keep user models
separate. See [Windows package setup](../setup/WINDOWS_PACKAGE.md) for the
remaining clean-machine gate and distribution obligations.


## M11 complete English voice inventory

`models/english_catalog.py` reads a bundled pinned Piper JSON snapshot and shares
Kokoro voice IDs with the installer/provider factories. The developer-only
catalog updater verifies LFS hashes and Git identities for configs/cards; no
runtime network discovery is added. Existing Kokoro/Lessac installation
identities remain compatible. ProviderManager describes every model without
loading weights; Piper validates the selected installation on first load and
switches lazily between model sessions. Numeric speaker selection is separate
from model identity, so speakers in a shared model reuse one CPU session.
Stable per-speaker IDs and catalog digests separate preview cache entries.
Desktop searches use metadata only; required-file presence is a quick hint,
while complete integrity checks and inference remain in background workers.
The library retains per-model download/removal transactions and notices.

## M12 structured document contract

`conversation_document.py` is a standalone JSON document layer with frozen
speaker/segment/speech records, bounded path-based diagnostics, guarded UTF-8
parsing, source/extension round-trip and explicit atomic Save As. Fresh imports
receive fresh active identities; validated edits or explicit reloads retain
identity and advance revision independently of content hashes. Defensive source
copies keep worker snapshots isolated. The module imports no UI/provider/model
code and leaves the legacy parser, service and all generation paths untouched.
See the [format/API guide](../JSON_DOCUMENT_FORMAT.md). The additions below
extend this contract without changing its legacy parser boundary.


## M13–M17 structured workflow implementation

```text
main.py (no arguments) -> legacy service/text defaults
main.py (arguments) -> cli.py --------------------------+
app.py -> gui.py -> structured_editor.py                |
                       | document snapshots + mappings |
                       v                               v
             conversation_document.py -> speaker_mapping.py
                       |                      |
                       +----> service.py <----+
                                  |
                  generation.py (per-segment speed + timeline)
                                  |
              provider MP3/WAV -> cancellable PCM silence -> audio_export.py

gui.py -> project_storage.py -> bounded data-only project/preset files
```

speaker_mapping.py owns stable active-document/speaker/provider edits,
reconciliation/reset, assignment precedence, deterministic metadata defaults,
readiness hints, supported effective speed and preflight diagnostics. It never
initializes a model, downloads or discovers voices online. Exact display-role,
provider and locale keys are used only for explicitly enabled reusable preferences.
Current edits and matching project assignments remain stronger.

service.generate_conversation adds keyword-only document and voice_assignments
inputs. Structured requests always use generation.py; all used configuration and
chunk requests validate before job creation. Legacy text and unprocessed Edge
stream-copy routing remain intact. Resolved settings are carried through normalized
source spans without merging segments. JSON uses optional intra-segment sentence
pauses and one exact after-pause per segment, including the final segment.
Streaming silence runs in a cancellable worker. Existing validated export/layout/
normalization and atomic publication modules remain authoritative.

Generation metadata version 2 records document identity/revision, typed resolved
segment metadata, assignment/request hashes and ordered speech/silence states.
Private dialogue and note bodies are hashed rather than recorded. Isolated jobs
do not resume or reuse audio. Rapid Windows metadata publication has a bounded
10/30/100 ms retry for transient access/sharing/lock errors; permanent failures
propagate and final-audio safety is unchanged.

structured_editor.py contains a fixed number of Tk widgets around role/segment
Treeviews. Source edits validate before replacing the immutable document. Mappings
remain independent of filtering and row order. gui.py retains the legacy text tab,
provider/model controls, preview cache/player, export controls and worker cleanup.
Large JSON/text/project/preset reads and parsing run in revision-tagged workers;
stale results cannot replace newer state. Generation captures immutable snapshots.
The editor surface scrolls horizontally/vertically, reveals keyboard focus and
leaves action/status controls outside it. Advanced export controls are collapsible.
JSON uses its own dynamic role view; legacy two-slot controls appear in plain text.

project_storage.py owns version-one project and preset contracts, strict bounded
JSON decoding, immutable loaded snapshots and atomic explicit saves. It shares the
document decoder's duplicate/nonfinite/depth protection; the embedded document
keeps its original limits. Source locators are inert provenance. Opening a project
restores its provider visibly, clears previous active edits and restores all-provider
assignments, locale and processing/export preferences. Source JSON exports remain
separate from projects and presets.

cli.py selects explicit text/JSON input and validates optional provider voice maps
using the same resolver/service. ProviderManager supplies local or Edge sessions,
which close in finally. New explicit exports require explicit overwrite; main.main
and python main.py without arguments retain original behavior. gen_audio.py is
unchanged. No new dependencies or optional runtime imports were introduced.

Acceptance status: M13/M14 DONE. M15–M17 implementations pass the approved
fake-provider/synthetic-media verification, but remain BLOCKED on actual 150%/200%
Windows scaling and dependent completion gates. Only actual 100% host evidence
is recorded. This does not change M10's clean-machine BLOCKED status.
See [the verification report](../milestones/M13_M17_VERIFICATION.md).
