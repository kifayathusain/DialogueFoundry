# M18–M21 — Audio Director

Registered 2026-11-01 from the user's end-to-end implementation request.
This independent follow-up preserves M10 and M15–M17 BLOCKED and all historical
DONE statuses. Implementation proceeds in dependency order; missing actual
Windows scaling, configured LLM, local synthesis or listening evidence blocks
acceptance rather than being inferred from automated tests.

| ID | Stage | Acceptance |
| --- | --- | --- |
| M18 | Batch foundation | Stable scoped discovery, editable manual snapshots, collision preflight, atomic exports, failure policy, cancellation/retry and desktop workflow |
| M19 | AI direction | Real configurable local adapter, bounded versioned data-only plans, privacy gate, capability/cast review, retained manual corrections |
| M20 | Natural audio | Resolved eligible timing, local generated room/cues, scoped phone speech processing, shared multi-turn audition/export decisions |
| M21 | Integrated acceptance | Automated regressions, actual connection/local media/listening samples, Windows keyboard/scaling evidence and setup guide |

Each stage requires the repository coding standards completion gate. Advanced
overlap and a standalone external-agent transport remain follow-up work; the
planning and runner APIs themselves have no Tk dependency.

## Baseline trace

Clean working tree (Git fsmonitor disabled for status because its IPC failed).
`conversation_document.load_document` retains original field absence in
`to_dict`; parsed `DocumentSegment.pause_after_seconds` alone defaults to zero.
`speaker_mapping.resolve_document` applies current > project > document > enabled
preset > catalog precedence and segment > speaker > job speed.
`service.generate_conversation` preflights and delegates structured generation to
`generation.generate_processed_conversation`; providers produce speech chunks,
PCM silence is inserted once per segment including final, and `audio_export`
validates/atomically publishes WAV/MP3/M4A. Existing preview is single-role speech;
the Director needs a multi-turn excerpt through that same structured pipeline.

Implementation evidence and unmet gates follow.

## Implementation outcome — 2026-11-01

M18–M21 status: **BLOCKED on required acceptance evidence**, with implemented
behavior available in the desktop. Historical M10 and M15–M17 remain BLOCKED;
all historical DONE statuses are preserved. Independent code work continued
through the later stages without falsely completing their dependencies.

- M18: `ttsapp/director.py`, `director_runner.py`, `director_gui.py` add stable
  direct/recursive discovery, excluded/invalid counts, immutable file snapshots,
  case-insensitive collision checks, manual/preset settings, one provider per
  file, mixed-provider batches, atomic validated exports, selected retries,
  privacy-safe reports and cooperative file-boundary cancellation.
- M19: `director_planner.py` implements actual configurable HTTP JSON-mode
  chat completions, bounded metadata-first inventory and optional excerpts,
  explicit cloud consent, strict version-one plans, unsupported/ambiguous request
  review, retained explicit casting and manual corrections. A model-generated
  path, command, FFmpeg expression, URL, voice/effect invention or unknown speaker
  cannot become an operation. Provider substitutions require explicit review.
- M20: `audio_effects.py` owns deterministic local room/cues and scoped phone
  filtering before combination. `service.py`/`generation.py` accept additive
  typed segment treatments, validate before job creation and record treatment
  identity. Plan snapshots freeze context-sensitive eligible gaps. Original and
  Directed use one selected exchange; Directed and export share cast, timing
  decisions and effects. Exact scripted zero/positive/final silence survives.
- M21: public fixtures, connection/real-synthesis helpers, tests,
  [user guide](../setup/AUDIO_DIRECTOR.md), README, document-contract clarification
  and architecture updates are delivered. Advanced overlap and an external agent
  transport remain explicit follow-up work. No new dependency was added.

The original CLI and existing structured editor remain unchanged in behavior.
Main-app shutdown now waits for Director and model-library cleanup. Provider
session closure runs in a worker, and stale/cancelled scan/plan/audition results
cannot overwrite the active state. Verification labels belong to exact settings
snapshots, so a later manual voice edit cannot retain a stale availability claim.

## Automated verification

Environment: Windows development host, CPython 3.13.17, pytest 9.1.1, Ruff 0.17.2,
FFmpeg/FFprobe 9.0.2 on PATH. Existing local interpreters/libraries were reused.
Windows asyncio/local fake HTTP requests require permitted execution outside
the restricted sandbox. No external network is used by automated tests.

Full-suite command from the repository root:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:TTS_FFMPEG_TESTS='1'
$env:TTS_EXPORT_TESTS='1'
$env:TTS_MODEL_DOWNLOAD_TESTS='0'
$env:TCL_LIBRARY=(Resolve-Path .venv-backup/python313-official/tcl/tcl8.6).Path
$env:TK_LIBRARY=(Resolve-Path .venv-backup/python313-official/tcl/tk8.6).Path
.\.venv-backup\python313-official\python.exe -m pytest -q --basetemp=.venv/director-full-suite -o cache_dir=.venv/director-cache --tb=short
```

Result: **506 passed, 11 skipped in 93.80 seconds**, no failures. Skips require
opt-in Piper/Kokoro/long-form/model-library download/preview/English-voice/package
fixtures or explicit playback opt-in. No model download, full voice validation,
benchmark, package rebuild or release is implied. Representative actual local
inference is separately recorded below rather than enabling unrelated campaigns.

The new test files are `tests/test_director.py`, `test_director_planner.py`,
`test_director_audio.py`, and `test_director_gui.py`. They cover scope/collisions,
invalid sources and changed fingerprints; omission versus explicit timing;
manual retention; forged settings/paths/voices/effects; metadata privacy and
offline/cloud blocking before requests; a real loopback fake HTTP protocol and
stalled-request cancellation; continue/stop/retry and existing-output protection;
real FFmpeg WAV/MP3/M4A, frequency attenuation and exact silence; native desktop
scan/audition/generate/report/retry/stale results; presets and close cleanup.

Intermediate findings were corrected and not hidden: the first foundation run
had one incorrect test expectation for the minimum short-reply gap (36 other
tests passed); the first proposal test used tuple-valued Python settings where
the JSON contract requires arrays (24 other tests passed). One native audition
was cancelled by a queued unchanged selection; it now cancels only on an actual
selection change. An earlier broad run had a legacy structured-GUI 20-second
timeout during concurrent real synthesis and a focus assumption in the new GUI
test; the subsequent complete-suite run above passed after removing concurrent
desktop/model work and establishing native focus. A later combined two-GUI
focused run passed 35 cases but hit the embedded runtime's existing `tk.tcl`
reinitialization error in 18 older-editor fixture setups; final GUI checks run
in separate processes rather than suppressing that runtime error.

Final post-review verification:

```powershell
# Same environment as above, with each command in its own process.
.\.venv-backup\python313-official\python.exe -m pytest tests/test_director.py tests/test_director_planner.py tests/test_director_audio.py tests/test_director_gui.py tests/test_service.py -q --basetemp=.venv/director-final-verified -o cache_dir=.venv/director-cache --tb=short
.\.venv-backup\python313-official\python.exe -m pytest tests/test_structured_gui.py -q --basetemp=.venv/director-legacy-gui-verified -o cache_dir=.venv/director-cache --tb=short
.\.venv-backup\python313-official\python.exe -m pytest tests/test_director_planner.py -q --basetemp=.venv/director-planner-final -o cache_dir=.venv/director-cache --tb=short
```

Results: **39 passed in 16.34 seconds**, **18 passed in 34.99 seconds**,
and **21 passed in 4.12 seconds** respectively, no skips/failures. These include
the final preset round trip, frozen after-pauses, exact verification identities,
explicit Tab traversal, asynchronous session/preview cleanup and malformed
endpoint recovery. The last adapter run follows the short five-second connection
timeout adjustment (inference responses retain their configured 90-second default).
The full-suite 506/11 result above predates four added endpoint-validation cases;
the final focused commands cover those additions without claiming a new full
suite count. No unresolved introduced failure remains in the verified scope.

### Coding standards gate

All 14 changed Python files pass `ruff format --check` and `ruff check` with
`.venv-backup/quality-tools/bin/ruff.exe`, and parse with `ast.parse(...,
feature_version=(3, 10))` under the recorded interpreter:

```text
ttsapp/audio_effects.py
ttsapp/director.py
ttsapp/director_runner.py
ttsapp/director_planner.py
ttsapp/director_gui.py
ttsapp/service.py
ttsapp/generation.py
ttsapp/gui.py
tests/test_director.py
tests/test_director_planner.py
tests/test_director_audio.py
tests/test_director_gui.py
scripts/check_director_llm.py
scripts/director_acceptance.py
```

Repository-wide `ruff check .` retains only pre-existing I001 in
`tests/test_parser.py`. `ruff format --check .` retains four pre-existing files:
`gen_audio.py`, `tests/test_audio_combiner.py`, `tests/test_parser.py`, and
`tests/test_tts_engine.py`. No rules were disabled and no unrelated bulk cleanup
was performed. `git -c core.fsmonitor=false diff --check` passes. Manual review
checked readable typed snapshots, focused UI sections, explicit errors/control
flow, source/script integrity, bounded model responses, no arbitrary execution,
privacy, cancellation/cleanup and additive service boundaries. Required real
acceptance gaps below prevent DONE despite passing code checks.

## Actual local synthesis and media evidence

Existing verified assets:
`C:\Users\kifay\AppData\Local\Windows TTS App\models\kokoro-82m-v1`.
The relocated runtime's `Scripts/python.exe` has a stale interpreter locator;
the existing official 3.13 interpreter can use its already-installed packages:

```powershell
.\.venv-backup\python313-official\python.exe -c "import sys,runpy; from pathlib import Path; sys.path.insert(0,str(Path('.venv-backup/kokoro-runtime/Lib/site-packages').resolve())); sys.argv=['scripts.director_acceptance','--model-directory','C:/Users/kifay/AppData/Local/Windows TTS App/models','--output','.venv/director-real-acceptance']; runpy.run_module('scripts.director_acceptance',run_name='__main__')"
```

The helper requires a fresh output folder. Python DNS/connection helpers were
denied after event-loop initialization; all model/phonemizer/effect assets were
local. No download occurred. British `bf_emma` and `bm_george` rendered original
fixture dialogue; `alex` was explicitly linked across discussion/interview.
Only `guest` in turns 2–4 received phone treatment. Results:

| Input | Result | Validated MP3 duration |
| --- | --- | --- |
| 01_narration.json | Completed under renamed destination; existing sentinel retained | 5.257958 s |
| 02_discussion.json | Completed | 9.506250 s |
| 03_telephone_interview.json | Completed | 18.951625 s |
| 04_malformed.json | Failed preflight: undeclared speaker; valid files retained | No output |

Local artifacts (ignored `.venv`, no binary audio added to Git):

- `.venv/director-real-acceptance/acceptance-report.json`
- `.venv/director-real-acceptance/telephone-directed-exchange.wav` — two-turn audition
- `.venv/director-real-acceptance/03_telephone_interview.mp3` — full listening sample
- `.venv/director-real-acceptance/telephone-full-decoded.wav` — decoded PCM evidence

FFmpeg decoded the full telephone file to 24 kHz PCM16. The final **1.8 seconds
have maximum absolute sample magnitude 0**, confirming retained ending silence
independently of the synthetic tests. One existing phonemizer word-alignment
warning occurred; exports validated, but no listening quality judgment is inferred.
Human intelligibility, host/guest differentiation and naturalness: **pending**.

## Actual Windows and LLM evidence; remaining prerequisites

The workspace was opened in the actual Tk app and inspected using the computer-use
skill. Native fake-provider tests exercise the desktop job at 1024×768. System
DPI is **96 (100%)**, screen **1920×1080**. Scrollbars and fixed job controls are
present; text fields have explicit Tab/Shift-Tab traversal and focus reveal.
These checks do not establish an all-controls keyboard/scaling pass at other
OS settings. Actual **150% and 200% OS scaling** remain untested; no Windows
display setting was changed and Tk font scaling is not substituted for OS DPI.

The actual default endpoint `http://127.0.0.1:11434/v1/models` was checked with
a two-second connection timeout and did not respond. No configured local model
name/alternate endpoint was supplied. The adapter's actual HTTP/JSON behavior is
proven with a loopback fake server, **not a real configured LLM inference run**.
To complete M19/M21: run an OpenAI-compatible local server with a local instruction
model, pass `scripts.check_director_llm`, then build/review the example instruction
in the desktop against the acceptance folder and record the actual plan/result.

Remaining acceptance gates:

- [x] Implemented desktop/services/manual/AI adapter/natural-audio feature and docs.
- [x] Relevant automated checks, complete suite, changed Ruff, existing findings,
      Python compatibility, synthetic exports and real representative local media.
- [x] Manual readability, privacy, architecture, error/cancellation/cleanup review.
- [ ] Configured real LLM produces the example plan and drives reviewed generation.
- [ ] Human listener confirms intelligibility, local/remote distinction and ending.
- [ ] Actual Windows 150%/200% scaling and complete keyboard usability evidence.

No missing gate is inferred passed. M18–M21 remain BLOCKED; this also preserves
every prior clean-machine and scaling blocker without a waiver.
