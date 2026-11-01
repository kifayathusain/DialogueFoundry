# M13 — Role-to-voice mapping and effective settings

Initial status: NOT_STARTED. Dependency: M12 DONE. Read shared rules before editing.

## Objective

Resolve every declared role to a deterministic, editable provider voice and resolve effective generation settings without relying on widget positions or loading voice models.

## Implementation tasks

1. Introduce pure mapping/state helpers, preferably `ttsapp/speaker_mapping.py`. Model speaker ID, role, provider, selected stable voice ID, assignment origin, readiness hint and warnings independently of Tk variables.
2. Implement the shared precedence rules and deterministic fallback algorithm. Validate candidate imported/preset defaults using metadata; invalid hints produce warnings and fall through. Invalid explicit current/project assignments remain visible unresolved errors instead of being silently replaced.
3. Retain state under active document ID + speaker ID + provider ID. Same-document reload reconciles retained IDs; new-document imports start fresh unless an explicitly loaded matching project supplies assignments. Removing then creating a different role must not inherit stale state.
4. Preserve voice selections across provider switches and filtering. Filtering changes available suggestions, not selection identity. Resolve Piper using full catalog voice IDs, keeping model IDs and numeric speakers separate from application roles.
5. Populate all declared roles, including unused ones. Check generation readiness only for used roles. An absent local model gets a labeled catalog default, never an automatic download. Do not claim file presence proves integrity.
6. Support custom nonempty Edge IDs as today. When the two configured Edge defaults serve three roles, reuse deterministically and emit shared-voice diagnostics identifying affected roles.
7. Resolve speed as segment > role > job > provider default; retain the source of each effective override. Validate 0.5–2.0 and declared provider support. Do not turn an untouched disabled Edge speed widget into an explicit speed request.
8. Produce resolved segments with source identity/index, selected voice, dialogue, effective speed, pause and direction-status metadata, ready for M14. Keep source notes out of spoken text.
9. Distinguish informational note-only directions, partially supported requirements and unsupported explicit settings. Do not interpret prose into guessed speed, pitch or emotion.
10. Provide preflight data: role/used-role count, segments, word count with documented counting convention, exact silence total, errors and warnings. Do not present a calculated speech duration as measured output.
11. Provide reset-role/default and reset-unmapped helpers that cannot overwrite unrelated manual assignments. Persistent preferences are passed in as data here; M16 implements storage.

## Expected files

Mapping/resolution helpers, small additive desktop-option/shared representation changes and focused tests. Reuse provider metadata and existing model status APIs; do not expand Edge capabilities or rewrite provider/session code.

## Required acceptance

- All sample roles receive populated defaults. A repeated Edge voice is warned about, not represented as distinct.
- Given the same inputs, catalog order and preferences, resolution is repeatable.
- Row/segment reordering, insertion/deletion, search and provider switching preserve the right manual choices.
- New documents with identical role names do not inherit another document's edits.
- Same-document retained IDs reconcile safely; source identity and revision are not conflated.
- Missing/corrupt model readiness is actionable; metadata resolution neither downloads nor infers.
- Imported invalid hints fall through visibly; invalid explicit edits block used-role generation.
- All speed precedence combinations propagate correctly; explicit Edge speed fails before synthesis.
- Direction notes are preserved and limitations are honest; only dialogue is synthesis content.
- Unknown provider defaults can remain preserved extensions/hints without selecting an unsupported provider.

## Verification and completion

Use fake catalogs/status sources and parameterized pure-function tests for precedence, ties, shared voices, model hints and identity transitions. Run audited existing desktop-options/catalog regressions. Record M13 evidence and the interface M14 will consume. Do not redesign the GUI yet.

## M13 implementation evidence — 2026-10-26

Status: DONE. Added pure `speaker_mapping.py` with stable document/speaker/provider
edit state, reconciliation and targeted resets, metadata-only deterministic defaults,
manual > matching project > imported > opt-in exact role/provider/locale preference
> catalog precedence. Locale, file-presence hint, unused voice and catalog order
break ties in that order. Invalid explicit selections remain unresolved; invalid
hints warn and fall through. All roles populate; only used roles block readiness.
Full stable local IDs and custom Edge IDs are preserved. Shared voices and
note-only directions are diagnosed honestly. Speed resolves segment > role > job
> provider, with explicit unsupported Edge speed rejected. Preflight counts words
using whitespace splitting, roles/used roles and exact explicit silence.
M14 consumes frozen ResolvedSegment snapshots; notes never become dialogue.

Audited new tests and existing M12 26-file allowlist (no conftest, third-party
plugins disabled, no ambient TTS opt-ins). Provider tests replace external adapters;
model transactions use tiny memory responses; enabled FFmpeg cases use non-speech
PCM only. Focused command:
`.venv-backup/python313-official/python.exe -m pytest tests/test_speaker_mapping.py tests/test_conversation_document.py tests/test_desktop_options.py tests/test_provider_manager.py -q --basetemp=.venv/m13-tests -o cache_dir=.venv/m13-cache --tb=short`
with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1: **175 passed**.
Broad command uses `Get-Content docs/milestones/M12_OFFLINE_TESTS.txt` plus
`tests/test_speaker_mapping.py`, same interpreter/options, basetemp
`.venv/m13-regression-permitted`, TTS_FFMPEG_TESTS=TTS_EXPORT_TESTS=1 and existing
`.venv-backup/ffmpeg-toolset` on PATH. Windows sandbox local asyncio socket-pair
stall was interrupted; permitted execution was used for the completed run.
Versions unchanged from M12: CPython 3.13.17, pytest 9.1.1, Ruff 0.17.2.

Changed-file Ruff format/check: both files pass. Repository Ruff: baseline I001 in
main.py and tests/test_parser.py; five unchanged format differences in gen_audio.py,
main.py, tests/test_audio_combiner.py, tests/test_parser.py, tests/test_tts_engine.py.
No suppressions or unrelated formatting. Manual review passes focused typed
responsibilities, explicit errors/control flow, privacy and architecture boundaries.
New tests cover precedence, invalid hints/explicit choices, missing/unused models,
ranking, sample sharing, identity/reorder/delete/reset/provider restoration and
all effective-speed sources/invalid values. Existing cancellation/cleanup checks
are in the broad allowlist. Exclusions remain exactly M12's excluded files/reasons;
no downloads, live synthesis, listening, quality work, benchmarks or M11 rerun.

Completion gate: acceptance, changed Ruff, repository findings, audited regressions,
failure/cleanup, manual readability, preserved architecture and documentation pass.
Historical M10 remains BLOCKED. No M13 required gate is unavailable.

Completed broad result: **379 passed in 10.65 seconds**, no skips/failures.
