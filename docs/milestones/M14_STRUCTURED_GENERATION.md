# M14 — Structured generation and exact segment pauses

Initial status: NOT_STARTED. Dependency: M13 DONE. Read shared rules before editing.

## Objective

Generate structured conversations through the existing service with correct voices, effective settings, chunk order and explicit silence, preserving legacy generation behavior.

## Implementation tasks

1. Add a keyword-only typed-document input to `generate_conversation` or a small service wrapper. Reject simultaneous explicit document/text sources. Preserve text-over-default-file behavior and all existing positional calls; document how explicit file inputs select their format.
2. Complete document/mapping/settings/output validation before any synthesis or job-file creation. Asset checks remain in workers. Preflight all used voices/configurations so a later segment's invalid settings do not cause partial synthesis.
3. Extend the resolved/chunk representation additively. Preserve segment identity, speaker, full voice ID, effective speed and normalized source span through each chunk. Never merge across source segments or setting changes.
4. Build ordered speech and silence items. Insert optional sentence pauses only inside a segment; insert each explicit after-pause exactly once after its last speech chunk, including the last segment. Do not add implicit paragraph silence at JSON boundaries.
5. Route JSON through processed generation, including Edge. Retain native MP3 Edge synthesis and decode once into the existing PCM path; preserve the legacy unprocessed Edge fast path for legacy requests.
6. Reuse streaming cancellable silence writing. Match source PCM layout or prepare it through the existing exporter. Do not hold a 600-second buffer or sleep in real time. Keep legacy text pause bounds unchanged.
7. Pass effective speed separately for every speech chunk using the existing provider request. Preserve one-provider sessions, lazy Piper model switching and full stable voice IDs.
8. Reuse WAV/MP3/M4A export, layout conversion, normalization, overwrite checks, timeout/cancellation and atomic output publication. Make no broad audio-module changes unless a concrete test exposes a gap.
9. Extend/version `generation.json` for resolved segment identity, timeline item order, settings, assignment hashes and silence durations/states. Include changes in pauses, mappings and applied speed in request identity. Hash private notes/text in diagnostics. Do not implement implicit chunk reuse/resume.
10. Preserve old per-line progress callback shape, adapting resolved segments as needed; report a segment complete after its planned speech and after-pause are materialized. Additive chunk/stage events may give finer detail. Keep progress monotonic and failures/cancellation correctly recorded.
11. Check cancellation during inference, decoding, silence writing and export, including task cancellation while a blocking worker is cleaning up. Preserve completed parts as existing behavior allows and remove incomplete temporary files.

## Required acceptance

- Fake synthesis sees only source dialogue chunks with the intended voice/speed; no metadata becomes speech.
- Reassembled normalized chunks cover each source segment exactly once and in order.
- Sample timeline has 26 segment after-pauses totaling 84 seconds, including the trailing 30 seconds; chunk count may exceed 26 without duplicating pauses.
- Zero adds no silence; fractional/long pauses have `round(rate × seconds)` frames; final silence survives PCM joining and exports.
- Optional sentence pauses add only their documented intra-segment silence. JSON paragraph whitespace adds no extra segment-boundary pause. Legacy paragraphs retain old behavior.
- Fake online MP3 exercises decoding; fake offline WAV exercises direct PCM. No real provider is invoked.
- Synthetic mixed-layout fixtures export to WAV/MP3/M4A using installed FFmpeg within existing codec tolerance, including with normalization.
- Failure or cancellation preserves an existing final file, avoids stale audio inclusion, records the right job state and cleans incomplete output.
- Validation fails before synthesis/job side effects; used-role missing model errors are actionable.
- Audited legacy service/generation/export tests still pass; custom voice IDs, defaults and callback consumers work.

## Verification and completion

Add fake-provider structured service/generation tests and synthetic-media integration tests. Use deterministic non-speech fixtures to verify durations and final silence, not listening. Test cancellation at each relevant stage and modified metadata hashes. Do not run live TTS, model integrations, benchmarks or exhaustive voice tests. Record M14 evidence and any absent FFmpeg prerequisite; missing required media checks cannot be called a pass.

## M14 implementation evidence — 2026-10-26

Status: DONE. The additive keyword-only service document/voice_assignments inputs
use M13 preflight and route all structured providers through processed generation.
Explicit text/file conflicts fail. All chunks/configurations and export targets
validate before job creation/synthesis. Legacy positional/text paths remain intact.
No paragraph gaps are introduced by JSON boundaries; optional intra-segment
sentence pauses and one explicit after-pause per segment are planned separately.

Version 2 generation metadata records document identity/revision, resolved voices,
per-segment effective speed/source and ordered speech/silence states, without source
dialogue or private notes. Request hashes include source content, mappings, speed
and pauses. Native Edge MP3 decodes once per chunk; local PCM remains native.
After-silence is streamed in cancellable workers using round(rate * seconds),
including final silence. Zero-frame rounded durations materialize no file. Existing
export preparation reconciles layouts and handles normalization, validated codecs,
cancellation, overwrite and atomic publication. Legacy fast Edge routing is retained.

Environment/tools match M12. Reviewed new test fixtures synthesize only bounded
programmatic non-speech PCM or copy a synthetic MP3; no external provider is called.
Focused M14/legacy run: 53 passed and one transient Windows atomic metadata replace
PermissionError; isolated changed/relevant recheck: 31 passed, failure not reproduced.
Broad allowlist (M12_OFFLINE_TESTS.txt plus test_speaker_mapping.py and
test_structured_generation.py) initially passed 400 cases. Final verification adds
normalized WAV/MP3/M4A coverage and accurately records completed speech when an
after-pause is cancelled. Exact command from repository root:

    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
    $env:TTS_FFMPEG_TESTS='1'
    $env:TTS_EXPORT_TESTS='1'
    $env:PATH=(Resolve-Path .venv-backup/ffmpeg-toolset).Path+[IO.Path]::PathSeparator+$env:PATH
    $auditedTests=Get-Content docs/milestones/M12_OFFLINE_TESTS.txt
    .\.venv-backup\python313-official\python.exe -m pytest @auditedTests tests/test_speaker_mapping.py tests/test_structured_generation.py -q --basetemp=.venv/m14-final -o cache_dir=.venv/m14-cache --tb=short

Runs use permitted execution for Windows asyncio local socket-pair support.
Sample proof: 26 after-pause items, 84 * 16000 exact zero PCM frames, last 30 seconds,
monotonic 26 segment completions, ordered source span coverage and dialogue-only
fake requests. Zero, sub-frame, fractional and 600-second silence cases pass.
Failure/cancellation preserve prior output; blocking decode/silence/export workers
finish cleanup before cancellation returns. Synthetic MP3 decode and WAV/MP3/M4A
exports retain trailing silence within codec tolerances, with/without normalization.
Existing synthetic mixed-layout, timeout/export and legacy regressions pass.

Changed-file commands:
`ruff.exe format --check ttsapp/service.py ttsapp/generation.py tests/test_structured_generation.py`
and `ruff.exe check` on the same paths (existing .venv-backup/quality-tools/bin).
Repository-wide format/check retain the same five format differences and two I001
findings listed in M13; no introduced findings or suppressions.
Manual review passes readable typed additive interfaces, focused responsibilities,
explicit control flow/errors, one provider per job, hashing privacy and resource
cleanup. M12 excluded test files/reasons remain excluded; no prohibited activity
or clean-machine/provider-quality claim. No required M14 gate unavailable.

Normalization fixture correction: the first added cases used DC-level near-silent
PCM, correctly rejected by the exporter as unmeasurable. Replaced the media-only
fixture with a one-second 440 Hz non-speech tone per request; no export relaxation.

Final corrected command uses basetemp .venv/m14-final-tones: **403 passed in
19.24 seconds**, no skips/failures. Three changed files pass Ruff format/check.
Completion gate passed: acceptance, audited regressions, cancellation/cleanup,
Ruff/manual review, compatibility and documentation.

M17 integration follow-up: typed per-segment metadata and explicit assignment
hash; bounded Windows sharing-error metadata retries. Final approved 31-file
regression: 457 passed. See [current verification](M13_M17_VERIFICATION.md).
