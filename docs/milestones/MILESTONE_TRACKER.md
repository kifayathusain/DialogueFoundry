# Milestone Tracker

## Status preservation

No milestone tracker or recorded milestone statuses existed in this checkout
when this file was introduced. “Not recorded” preserves that uncertainty; it is
not a claim that existing application work is incomplete or absent. Verify the
historical status before assigning NOT_STARTED, IN_PROGRESS, BLOCKED, or DONE.
Do not infer completion from source files, old milestone labels, or this policy
change. Existing completed application features remain intact.

Follow the [master plan](MASTER_PLAN.md) sequentially and the authoritative
[coding standards](../CODING_STANDARDS.md). All milestones require the same
coding standards compliance review before a new DONE transition. Preserve any
established status on later edits and record compliance evidence separately.

## Milestones

| ID | Scope | Recorded status | Coding standards compliance |
| --- | --- | --- | --- |
| M01 | Baseline Review and Architecture | DONE | Passed; [evidence](M01_BASELINE.md) |
| M02 | Provider Abstraction and Edge Migration | DONE | Passed; [evidence](M02_PROVIDERS.md) |
| M03 | Piper Offline Provider | DONE | Passed real CPU/media gate; [evidence](M03_PIPER.md) |
| M04 | Kokoro Natural Voice Provider | DONE | Passed real CPU/media gate; [evidence](M04_KOKORO.md) |
| M05 | Model Library and Download Manager | DONE | Passed fresh-model/UI gate; [evidence](M05_MODEL_MANAGER.md) |
| M06 | Text Chunking and Natural Speech Processing | DONE | Passed real long-form and user listening; [evidence](M06_TEXT_PROCESSING.md) |
| M07 | Voice Preview and UI Improvements | DONE | Passed real preview/UI/playback gate; [evidence](M07_PREVIEW_UI.md) |
| M08 | High-Quality Export System | DONE | Passed real codec/UI/media safety gate; [evidence](M08_EXPORT.md) |
| M09 | Performance Optimization | DONE | Passed real benchmarks/lifecycle/regressions; [evidence](M09_PERFORMANCE.md) |
| M10 | Windows Packaging and Final QA | BLOCKED | Local standalone tests pass; clean Windows 11 evidence required; [details](M10_PACKAGING.md) |
| M11 | Complete British and American English Voice Library | DONE | Passed all 2,034 CPU voice checks, Windows UI/media and regression gate; [evidence](M11_ENGLISH_VOICES.md) |
| M12 | JSON Document Contract and Validation | DONE | Passed audited offline document/regression gate; [evidence](M12_JSON_DOCUMENT_CONTRACT.md) |
| M13 | Role-to-Voice Mapping and Effective Settings | DONE | Passed offline mapping gate; [scope](M13_ROLE_VOICE_MAPPING.md) |
| M14 | Structured Generation and Exact Segment Pauses | DONE | Passed fake-provider/synthetic-media gate; [scope](M14_STRUCTURED_GENERATION.md) |
| M15 | Responsive Multi-Speaker Windows GUI | BLOCKED | Native fake-provider UI passes at 100%; required 150%/200% OS scaling evidence missing; [scope](M15_RESPONSIVE_GUI.md) |
| M16 | Saved Projects, Presets and JSON CLI | BLOCKED | Implemented/tested; M15 dependency gate remains open; [scope](M16_PROJECTS_PRESETS_CLI.md) |
| M17 | Integrated Acceptance and Documentation | BLOCKED | Integrated safe checks/docs pass; M15/M16 completion gates remain open; [scope](M17_INTEGRATED_ACCEPTANCE.md) |
| M18 | Audio Director Batch Foundation | BLOCKED | Implemented/tested; actual 150%/200% Windows usability gate remains open; [evidence](M18_M21_AUDIO_DIRECTOR.md) |
| M19 | Audio Director AI Direction | BLOCKED | Implemented/protocol tested; configured real LLM run unavailable; [evidence](M18_M21_AUDIO_DIRECTOR.md) |
| M20 | Audio Director Natural Audio | BLOCKED | Real local Kokoro/media checks pass; human listening judgment pending; [evidence](M18_M21_AUDIO_DIRECTOR.md) |
| M21 | Audio Director Integrated Acceptance | BLOCKED | Full suite passes; actual LLM/listening/150%/200% QA gates remain open; [evidence](M18_M21_AUDIO_DIRECTOR.md) |

“Pending” means the milestone has not been reviewed against the new gate. The
standards/configuration update does not complete or reopen an application
milestone. The [initial validation report](CODING_STANDARDS_VALIDATION.md)
records existing tests and pre-existing Ruff findings separately.

## Mandatory completion record for every milestone

Copy this checklist into the milestone's evidence entry before marking DONE:

- [ ] Milestone acceptance criteria are met; applicable real-model and Windows
      checks have recorded results.
- [ ] Ruff formatting and lint checks pass for changed Python files, with exact
      commands and results.
- [ ] Repository-wide Ruff results are recorded; pre-existing violations are
      listed separately by file/rule and introduced regressions are resolved.
- [ ] Existing tests and tests for changed behavior pass, covering applicable
      failure paths, cancellation, and resource cleanup.
- [ ] Manual readability review passes: meaningful names, focused functions,
      explicit control flow, suitable type hints/docstrings and error handling,
      no compressed statements, and no unnecessary abstractions.
- [ ] Existing features, architecture boundaries, and unrelated work are preserved.
- [ ] Documentation is current and limitations are recorded.

Record the date, interpreter/tool versions, changed scope, commands, results,
review findings, and any required checks that could not run. Required missing
validation or introduced failures prevent DONE; use BLOCKED with a reproducible
reason when a milestone fails its completion gate. Do not turn a historical
DONE into a new compliance pass without evidence.

## Evidence entries

### Audio Director implementation and acceptance — 2026-11-01

M18–M21 are implemented as an independent follow-up in stage order, with shared
Tk-independent plans/runner, manual batches, an actual configurable LLM adapter,
validated data-only decisions and common audio processing. No historical status
has changed. Missing real LLM, human listening and OS scaling evidence keeps the
new milestones BLOCKED; implemented files are not a completion waiver.

[Full commands, results, traceability and prerequisites](M18_M21_AUDIO_DIRECTOR.md).
The complete suite passed **506 tests, 11 opt-in skips in 93.80 seconds**. All 14
changed Python files pass relevant Ruff and Python 3.10 syntax parsing; the
existing I001 in `tests/test_parser.py` and four untouched format differences
remain separate. Real British Kokoro generated three valid MP3 lessons, preserved
an output conflict, reported the malformed source, and produced a scoped phone
audition. The full phone export decodes to 18.951625 seconds at 24 kHz; its final
1.8 seconds have exactly zero PCM magnitude. Listening approval remains pending.
No model download, package rebuild, exhaustive voice campaign, commit or push.
Final post-review checks pass **39 Director/service**, **18 legacy Windows UI**
and **21 planner** cases in separate processes. The full-suite total predates
four added invalid-endpoint cases; exact commands and the embedded Tcl/Tk
combined-process limitation are recorded in the linked evidence.

### M12–M17 authorization and registration — 2026-10-26

The user approved the JSON/multi-speaker follow-up and explicitly requested
M12 implementation using the packet. No ID conflicts were present. Registered
M12–M17 as NOT_STARTED, then began M12 (IN_PROGRESS). M13–M17 remain unimplemented.
The packet files already existed; their presence was not treated as acceptance.
These milestones may proceed independently of M10's clean-machine blocker,
without waiving it. M01–M09 and M11 retain DONE; M10 retains BLOCKED. The new
follow-up uses reviewed offline/fake-provider tests under the
[execution rules](M12_M17_EXECUTION_RULES.md), with no repeated voice validation.

### M12 completion — 2026-10-26

Gate passed: [full M12 evidence](M12_JSON_DOCUMENT_CONTRACT.md). Standalone typed
JSON parsing/validation, immutable source snapshots, extensions, identity/revision,
serialization and atomic Save As are implemented. Unmodified sample: three roles,
26 ordered segments, 84 seconds of explicit pause including the final 30 seconds.
Schema, guide, optional-field example and architecture documentation are current.

CPython 3.13.17 / pytest 9.1.1 / Ruff 0.17.2; exact commands and
[26-file audited allowlist](M12_OFFLINE_TESTS.txt) are recorded in M12. Focused:
157 pass; final broad fake-provider/synthetic-media regression: **364 pass**, no
skips/failures. Both new Python files pass Ruff format/lint and manual
readability/type/error/boundary review. Repository baseline remains I001 in
`main.py` and `tests/test_parser.py`, plus five untouched formatting differences.
Failure/cleanup and existing cancellation regressions pass. No M12 required gate
is unmet; document I/O has no cancellation API and no GUI import is claimed.

No downloads, real synthesis, quality/comparison/listening tests, benchmarks,
exhaustive voice checks, dependency installation, commit or push. Excluded tests
and the resolved sandbox asyncio restriction are recorded separately. M13–M17
remain NOT_STARTED; stop after M12. M01–M09/M11 retain DONE and M10 retains
BLOCKED on actual clean Windows 11 evidence, without a waiver or inferred pass.

### M11 authorization — 2026-10-25

The user explicitly authorized implementation of complete Kokoro/Piper British
and American English coverage as M11. Proceed with this scoped follow-up while
preserving M10 BLOCKED and M01–M09 DONE. This does not waive clean-machine QA.
See [M11](M11_ENGLISH_VOICES.md) for inventory, acceptance and validation evidence.

2026-10-24: Execution explicitly started at M01 after reviewing the existing
implementation and 44 passing baseline tests. Later roadmap milestones have
not been implemented; NOT_STARTED refers to this roadmap, not the absence of
existing desktop, Edge, or packaging functionality.


### M01 completion — 2026-10-24

Gate passed: [full M01 evidence](M01_BASELINE.md). Architecture/provider contract
reviewed; five regressions added; 49 tests pass; real Tkinter construction passes;
new tests pass Ruff lint/format and manual readability review. Pre-existing
26 lint violations/nine formatting differences are unchanged and separately
recorded. Missing FFmpeg and stale `.venv` are documented environment risks;
no live synthesis, real media, or listening result is claimed. M02 may begin.


### M02 completion — 2026-10-24

Gate passed after M01: [full M02 evidence](M02_PROVIDERS.md). Provider contracts,
registry, and compatible Edge routing implemented. All 70 tests and relevant
Ruff checks pass; manual readability/architecture review passes. Remaining
repository baseline: 18 existing lint violations and nine formatting differences
in untouched files. No offline/runtime or real FFmpeg result is claimed. M03 may
begin; do not start M04 until real offline Piper acceptance passes.


### M03 completion — 2026-10-24

Gate passed: [Piper evidence](M03_PIPER.md). Real verified voice generated
CPU-only WAV and a two-line MP3, with Python network calls blocked; FFmpeg decode
and duration/sample checks pass. 89 tests passed with the real model enabled;
88 pass/one opt-in skip without Piper installed. Changed files pass Ruff and
readability review. Remaining baseline: 15 existing lint violations/eight
formatting differences. M04 Kokoro-82M may begin.


### M04 completion — 2026-10-24

Gate passed: [Kokoro evidence](M04_KOKORO.md). Real unquantized Kokoro-82M runs
on CPU using verified local assets and signed supported Python; multi-voice
MP3 decodes correctly. Default regressions: 103 pass/two opt-in skips. Real-model
and provider subset: 35 pass. Relevant Ruff/readability review passes. CPU/PCM
benchmarks are recorded separately; human listening remains pending and no
naturalness claim is made. M05 model management may begin.


### M05 completion — 2026-10-24

Gate passed: [model-library evidence](M05_MODEL_MANAGER.md). Both catalog models
were freshly downloaded, verified, used on CPU offline, and removed. Two real
acceptance cases pass; default full suite 123 pass/four opt-in skips. Real Tkinter
library construction/queued verification and worker-thread tests pass. Relevant
Ruff/readability review passes. Remaining baseline: ten lint findings/seven
formatting differences in untouched files. M06 text processing may begin.


### M06 completion — 2026-10-24

Gate passed: [M06 evidence](M06_TEXT_PROCESSING.md). Full regressions plus real
FFmpeg case: 150 pass/five opt-in skips. Real long-form and both provider media
checks: three pass. User explicitly accepted the real Kokoro join sample:
“The joins sound acceptable.” Relevant Ruff/readability checks pass. Two
pre-existing import findings/six formatting differences remain outside scope.
M07 may begin.


### M07 completion — 2026-10-24

Gate passed: [M07 evidence](M07_PREVIEW_UI.md). Full suite 169 pass/seven opt-in
skips; real Kokoro/Piper preview/cache case passes; real Tkinter/Piper
responsiveness/cancellation/stale-result/cleanup and Windows playback cases pass.
Relevant Ruff/manual review passes. Two unrelated import lint findings and five
formatting differences remain. M08 export system may begin.


### M08 completion — 2026-10-25

Gate passed: [export evidence](M08_EXPORT.md). Full suite 198 pass/eight opt-in
skips. Real WAV/MP3/M4A, normalization, Unicode/mixed-layout, native-copy,
validation/overwrite/cleanup cases pass; actual Tkinter/Piper M4A/WAV export
and explicit replacement pass; real Kokoro speech validates across all formats.
Relevant Ruff/manual review passes; two unrelated import findings/five formatting
differences remain. M09 performance measurement/optimization may begin.


### M09 completion — 2026-10-25

Gate passed: [performance evidence](M09_PERFORMANCE.md). Real Kokoro/Piper/Edge
benchmarks and explicit startup/memory/throughput tradeoffs are recorded. Full
suite: 204 pass/eight opt-in skips; real provider/preview subset: 38 pass; Windows
UI/export: two pass/one playback skip (playback passed in full suite). Ten changed
Python files pass Ruff and manual review. Two existing import findings/five
formatting differences remain separate. M10 packaging may begin.


### M10 local QA — 2026-10-25

[Package evidence](M10_PACKAGING.md): concrete full Windows ZIP built and
extracted; real fresh model downloads, both offline CPU runtimes, Edge and all
three formats pass. Final suite 212 pass/nine opt-in skips; changed-file Ruff
and manual review pass. Two existing lint findings/five formatting differences
remain separate. BLOCKED on the master plan's clean Windows 11 gate: this host
is the development machine and Windows Sandbox is unavailable. The user has
the final artifact/hash and required checklist. Preserve M01-M09 DONE; mark
M10 DONE only after actual clean-machine evidence, never by inference. No
commit, push, public release or security-policy bypass occurred.

The user confirmed that a clean Windows 11 machine is not available. M10 remains
BLOCKED; no clean-machine pass or permission to skip the gate is inferred.

### M11 completion — 2026-10-25

Gate passed: [complete English voice evidence](M11_ENGLISH_VOICES.md). All 28
Kokoro voices and all 2,006 Piper speaker/quality choices across 38 pinned
British/American English model variants generated valid nonzero PCM using real
CPU inference with Python network connection helpers denied. Pinned metadata,
per-model downloads/notices, numeric speakers, lazy model/config session reuse,
search, model guidance and corrupt-preview prerequisite checks are implemented.
Existing Kokoro/Lessac installations remain compatible.

Final full suite: **235 passed, 11 opt-in skips**; real Windows search,
multispeaker previews, mixed-model generation and WAV/MP3/M4A export: **one
passed**. Native Windows playback passes in the full suite. All 17 changed/new
Python files pass Ruff and manual readability/architecture review. Repository
baseline remains I001 in `main.py`/`tests/test_parser.py` and five untouched
formatting differences, documented in M11. No introduced violations or unrelated
formatting. Exact commands, combined report hash and per-model counts are in M11.

A new local Windows QA ZIP contains the complete offline inventory; standalone
Kokoro/Piper and all formats pass with existing model installations and sanitized
environment paths. SHA-256:
`7656bd01335b3dcf1f47db83ccf20fa99ba6a43ebf67385ae8b1d89161b413d1`.
Temporary validation installations and redundant new build directories were
removed; earlier artifacts and user models remain intact. No human quality,
clean-machine, signing, public release, commit or push claim. M01–M09 remain
DONE; M10 remains BLOCKED exactly as authorized when M11 began.

### M13 completion — 2026-10-26

Gate passed: [M13 evidence](M13_ROLE_VOICE_MAPPING.md). Focused 175 passed;
audited broad regressions 379 passed. Two changed Python files pass Ruff and
manual readability/architecture review; repository baseline unchanged. Mapping,
identity, precedence, readiness, speed and notes gates pass in the approved fake
scope. Exclusions remain M12's documented list. M14 may begin; M10 stays BLOCKED.

### M14 completion — 2026-10-26

Gate passed: [M14 evidence](M14_STRUCTURED_GENERATION.md), 403 audited tests
passed including fake MP3/WAV, exact final silence, normalized WAV/MP3/M4A,
validation-before-side-effects and blocking-stage cancellation cleanup. Three
changed files pass Ruff and manual review; repository findings unchanged.
M15 may begin. Historical M10 remains BLOCKED.


### M13–M17 current authorization and integrated evidence — 2026-10-26

The user explicitly authorized sequential M13–M17 and automatic continuation.
The historical M12-only boundary above is preserved as that session's record.
M13/M14 gates passed in order before M15 implementation. After M15's required
OS scaling gap was established, independent storage/CLI, integration tests and
documentation continued under the user's blocker instruction. No downstream
DONE transition is inferred from implemented files or passing independent tests.

[Full verification and traceability](M13_M17_VERIFICATION.md);
[31-file audited allowlist](M13_M17_OFFLINE_TESTS.txt). Final broad result:
**457 passed in 37.25 seconds**, no skips/failures. Exact command uses
.venv-backup/python313-official/python.exe, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1,
TTS_FFMPEG_TESTS=TTS_EXPORT_TESTS=1, existing FFmpeg tools and Tcl/Tk paths,
basetemp .venv/m13-m17-verified and cache .venv/m13-m17-cache.
The report records prior failed/intermediate runs separately, including corrected
synthetic normalization fixtures/test assumptions and the bounded Windows metadata
sharing-error integration fix. No repeated voice testing occurred.

All 14 changed Python files pass Ruff format/lint and Python 3.10 syntax parsing.
Repository baseline now has I001 in tests/test_parser.py only and four untouched
format differences (gen_audio.py, tests/test_audio_combiner.py, tests/test_parser.py,
tests/test_tts_engine.py). main.py's prior findings were fixed within its CLI edit.
Manual readability/type/error/privacy/architecture review passes. No suppressions,
bulk formatting or unrelated changes. Exact tooling and exclusions are in the report.

- [x] M13/M14 required acceptance, tests, failure/cancel/cleanup, changed Ruff,
      repository findings, manual review, boundaries and documentation pass.
- [x] M15 implemented import/edit/mapping/validation/preview and responsive
      scrollable Tk controls; native fake-provider tests include 1/3/20/1000 roles,
      long labels/IDs, stale revisions, unsaved flows, cancellation and close.
- [x] M16 independent project/preset persistence and additive JSON CLI acceptance
      passes, including shared service parity and no-argument legacy behavior.
- [x] M17 integrated sample export/project/reopen/CLI and compatibility checks,
      traceability, exclusions and current guides/architecture are recorded.
- [ ] M15 actual Windows 150%/200% OS scaling and associated all-controls keyboard
      evidence. Host report: DPI96/100%, 1920×1080 screen, 1024×768 test window.
      Existing Windows Settings launch via Computer Use returned
      "Computer Use app approval timed out"; no display settings changed.
- [ ] M16 dependency gate: M15 DONE.
- [ ] M17 dependency/final gate: M15/M16 DONE.

M15/M16/M17 remain BLOCKED; implementation/testing is not a waiver. M12 and all
historical statuses/evidence are preserved, including M10 BLOCKED on clean Windows
11 acceptance. No downloads, real synthesis, voice-quality/comparison/listening
checks, benchmarks, exhaustive M11 validation, package rebuild, install, commit,
push or publication.
