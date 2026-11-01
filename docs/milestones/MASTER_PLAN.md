# TTS Milestone Master Plan

## Authorized Audio Director follow-up — 2026-11-01

The user requests sequential M18–M21 implementation, including actual local LLM,
local synthesis and Windows acceptance where prerequisites are available.
This supersedes older session-specific testing boundaries for this new work.
See [scope and gates](M18_M21_AUDIO_DIRECTOR.md). Existing statuses and outstanding
M10/M15–M17 acceptance remain unchanged; independent follow-up work may proceed.

## Authority and scope

Start every Codex session with [AGENTS.md](../../AGENTS.md). Follow the
[authoritative coding standards](../CODING_STANDARDS.md) for every milestone.
This plan carries forward the M01–M10 scope and acceptance criteria from the
existing [master implementation instructions](../Codex-Master-Implementation-Instructions.md).
It adds a mandatory compliance gate without changing the implementation order.

The milestone directory and tracker were absent when this plan was introduced.
No historical milestone statuses are inferred here. Existing Edge TTS, Tkinter
UI, CLI, FFmpeg exports, tests, and Windows packaging work remain intact.
Existing source references to a desktop UI “M02” predate this roadmap and do not
prove completion of the provider-abstraction M02 below.

Implement milestones sequentially. Review existing code before each change;
preserve application boundaries and completed work. Do not start provider
implementation or rewrite modules merely to adopt the coding standards.

## Shared compliance gate

Every milestone below includes the completion gate in
[CODING_STANDARDS.md, section 20](../CODING_STANDARDS.md#20-tooling-and-milestone-completion-gate):

- Pass relevant Ruff formatting and lint checks for changed Python files.
- Run repository-wide checks and existing automated tests; report pre-existing
  violations separately, without unrelated bulk formatting or suppressed rules.
- Add and pass tests for changed behavior, including applicable failure,
  cancellation, and cleanup paths.
- Review code manually for descriptive names, explicit control flow, focused
  responsibilities, type hints, docstrings, error handling, and no compressed
  statements or unnecessary abstractions.
- Preserve existing features and UI/service/provider/model/audio boundaries.
- Verify milestone acceptance criteria, including real-model or Windows checks
  where required, and update documentation.
- Record exact commands, results, limitations, and review evidence in the
  [tracker](MILESTONE_TRACKER.md) before DONE.

Required validation that cannot run blocks DONE. Historical statuses must be
preserved; record their compliance review separately rather than asserting that
older work passed a newly introduced gate. Once verified, use NOT_STARTED,
IN_PROGRESS, BLOCKED, or DONE as defined in the master instructions.

## Milestones

M11 is a user-authorized follow-up added on 2026-10-25 while M10 remains
BLOCKED. Its implementation may proceed independently; M10's clean-machine
completion gate remains required and unchanged.

### M01 — Baseline Review and Architecture

[Milestone document](M01_BASELINE.md)

- Review existing implementation.
- Record existing functionality.
- Document current architecture.
- Introduce baseline regression tests.
- Define provider contracts.
- Create milestone tracker.

**Acceptance:** Baseline application still works and architecture decisions are documented.

**Coding standards compliance:** Before DONE, complete the [shared compliance gate](#shared-compliance-gate) and record commands, results, readability review, and any pre-existing violations in the [tracker](MILESTONE_TRACKER.md).

### M02 — Provider Abstraction and Edge Migration

[Milestone document](M02_PROVIDERS.md)

- Introduce provider registry.
- Create common synthesis requests and responses.
- Move Edge integration behind provider interface.
- Preserve current UI and output behavior.

**Acceptance:** Existing Edge TTS generation passes all regression tests.

**Coding standards compliance:** Before DONE, complete the [shared compliance gate](#shared-compliance-gate) and record commands, results, readability review, and any pre-existing violations in the [tracker](MILESTONE_TRACKER.md).

### M03 — Piper Offline Provider

[Milestone document](M03_PIPER.md)

- Select an appropriate supported Piper implementation.
- Integrate local CPU synthesis.
- Add voice discovery.
- Implement model validation.
- Test real-model WAV generation.

**Acceptance:** A downloaded Piper voice produces valid audio with internet disabled.

**Coding standards compliance:** Before DONE, complete the [shared compliance gate](#shared-compliance-gate) and record commands, results, readability review, and any pre-existing violations in the [tracker](MILESTONE_TRACKER.md).

### M04 — Kokoro Natural Voice Provider

[Milestone document](M04_KOKORO.md)

- Evaluate maintained Kokoro ONNX runtimes.
- Choose a suitable CPU-compatible implementation.
- Integrate Kokoro-82M.
- Implement voice selection and lazy model loading.
- Add quality and CPU benchmarks.

**Acceptance:** Real Kokoro synthesis works offline on CPU-only Windows and produces valid audio through the existing export pipeline.

**Coding standards compliance:** Before DONE, complete the [shared compliance gate](#shared-compliance-gate) and record commands, results, readability review, and any pre-existing violations in the [tracker](MILESTONE_TRACKER.md).

### M05 — Model Library and Download Manager

[Milestone document](M05_MODEL_MANAGER.md)

- Implement model catalog.
- Add integrity-verified downloads.
- Add installation, deletion, and recovery.
- Add model management UI.

**Acceptance:** A fresh installation can download, validate, use, and remove supported models without administrator privileges.

**Coding standards compliance:** Before DONE, complete the [shared compliance gate](#shared-compliance-gate) and record commands, results, readability review, and any pre-existing violations in the [tracker](MILESTONE_TRACKER.md).

### M06 — Text Chunking and Natural Speech Processing

[Milestone document](M06_TEXT_PROCESSING.md)

- Implement sentence-aware chunking.
- Add paragraph pauses.
- Add text normalization.
- Improve long-form generation.
- Add output metadata and chunk tracking.

**Acceptance:** Long text generates in the correct order without missing or duplicated text, and output joins are audibly acceptable.

**Coding standards compliance:** Before DONE, complete the [shared compliance gate](#shared-compliance-gate) and record commands, results, readability review, and any pre-existing violations in the [tracker](MILESTONE_TRACKER.md).

### M07 — Voice Preview and UI Improvements

[Milestone document](M07_PREVIEW_UI.md)

- Implement provider/voice selection UI.
- Add short previews.
- Add playback controls.
- Add progress and cancellation.
- Improve desktop responsiveness.

**Acceptance:** Users can preview voices and configure audio generation without UI freezes.

**Coding standards compliance:** Before DONE, complete the [shared compliance gate](#shared-compliance-gate) and record commands, results, readability review, and any pre-existing violations in the [tracker](MILESTONE_TRACKER.md).

### M08 — High-Quality Export System

[Milestone document](M08_EXPORT.md)

- Refactor FFmpeg processing.
- Support WAV, MP3, and M4A.
- Add optional normalization.
- Validate exported media.
- Improve error handling.

**Acceptance:** All supported formats produce playable files with correct metadata and no unexpected truncation.

**Coding standards compliance:** Before DONE, complete the [shared compliance gate](#shared-compliance-gate) and record commands, results, readability review, and any pre-existing violations in the [tracker](MILESTONE_TRACKER.md).

### M09 — Performance Optimization

[Milestone document](M09_PERFORMANCE.md)

- Benchmark Kokoro, Piper, and Edge separately.
- Optimize CPU threads.
- Reduce memory usage.
- Improve caching.
- Optimize model lifecycle.
- Document measured results.

**Acceptance:** Real benchmark results are recorded and no unacceptable regression is introduced.

**Coding standards compliance:** Before DONE, complete the [shared compliance gate](#shared-compliance-gate) and record commands, results, readability review, and any pre-existing violations in the [tracker](MILESTONE_TRACKER.md).

### M10 — Windows Packaging and Final QA

[Milestone document](M10_PACKAGING.md)

- Package the application for Windows.
- Include or securely locate FFmpeg.
- Keep downloadable models separate from the base installer.
- Validate a clean-machine installation.
- Complete regression tests.
- Update documentation.

**Acceptance:** A clean Windows 11 environment can install, launch, download a model, synthesize offline audio, and export playable files.

**Coding standards compliance:** Before DONE, complete the [shared compliance gate](#shared-compliance-gate) and record commands, results, readability review, and any pre-existing violations in the [tracker](MILESTONE_TRACKER.md).

### M11 — Complete British and American English Voice Library

[Milestone document](M11_ENGLISH_VOICES.md)

- Expose all 28 official Kokoro-82M v1.0 British/American voices.
- Include every Piper en_US/en_GB model, quality variant and individual speaker
  in the pinned official inventory with verified downloads and model notices.
- Support selected-model lifecycle, speaker selection, search and previews.
- Preserve existing installations, Edge workflows and M10's blocked status.

**Acceptance:** Exact catalog coverage, offline synthesis of every exposed
voice/speaker, usable Windows selection/preview/model management, validated
representative exports, and the shared coding standards gate recorded in M11.

## Authorized M12–M17 follow-up — 2026-10-26

The user requested implementation beginning with M12 from the approved
JSON/multi-speaker packet. This follow-up may proceed independently of M10's
clean Windows 11 blocker; that gate and every historical status remain intact.
Follow the [shared execution rules](M12_M17_EXECUTION_RULES.md), especially the
mandatory offline/fake-provider verification boundary. See the
[packet entry point](START_HERE.md) and [registration rules](TRACKER_ADDITIONS.md).
Only M12 is authorized for implementation in this session. Later milestones
remain NOT_STARTED and must proceed sequentially when requested.

| ID | Scope | Dependency | Acceptance reference |
| --- | --- | --- | --- |
| M12 | JSON Document Contract and Validation | Existing architecture | [Typed validation and lossless source round-trip](M12_JSON_DOCUMENT_CONTRACT.md) |
| M13 | Role-to-Voice Mapping and Effective Settings | M12 | [Deterministic editable assignments](M13_ROLE_VOICE_MAPPING.md) |
| M14 | Structured Generation and Exact Segment Pauses | M13 | [Ordered speech/silence and final pause](M14_STRUCTURED_GENERATION.md) |
| M15 | Responsive Multi-Speaker Windows GUI | M14 | [Import/edit/mapping and responsive desktop](M15_RESPONSIVE_GUI.md) |
| M16 | Saved Projects, Presets and JSON CLI | M15 | [Persistence and additive CLI input](M16_PROJECTS_PRESETS_CLI.md) |
| M17 | Integrated Acceptance and Documentation | M16 | [Integrated safe acceptance](M17_INTEGRATED_ACCEPTANCE.md) |



## Current M13–M17 authorization and outcome — 2026-10-26

The user's new request supersedes the earlier M12-only session boundary above
and explicitly authorizes M13–M17 sequential implementation. M12's completed
implementation/evidence was the starting point. M13 passed before M14; M14 passed
before M15. M15 now has implemented structured UI behavior and safe Windows
acceptance at the reported 100% scale, but required actual 150%/200% OS scale
checks could not run (Windows Settings app approval timed out; no display changes).

Under the explicit instruction to continue independent authorized work when
blocked, project/preset persistence, JSON CLI, snapshot integration, compatibility
verification and documentation were implemented and tested. Their dependent
completion gates are not bypassed: M15, M16 and M17 remain BLOCKED. M13 and M14
are DONE. See [current verification](M13_M17_VERIFICATION.md) and
[the tracker](MILESTONE_TRACKER.md). Historical M10 remains BLOCKED; no downloads,
live synthesis, listening, benchmarking, M11 rerun, package rebuild or release
was performed. No mixed-provider orchestration or deferred feature was added.
