# M15 — Responsive multi-speaker Windows GUI

Initial status: NOT_STARTED. Dependency: M14 DONE. Read shared rules before editing.

## Objective

Provide a modern, keyboard-usable Tkinter workflow to import and edit structured conversations, configure any declared role, review validation and generate without UI freezes.

## Implementation tasks

1. Replace positional two-row state with the M12/M13 document and mapping state. Preserve the familiar plain-text editor and legacy initial names/voices. Extract focused view helpers where useful without replacing Tkinter or creating a second business-logic implementation.
2. Add Open/Import and explicit Plain text/JSON modes. Use extension or explicit format; malformed JSON must never fall back silently to plain text. Import into temporary state, then swap only after successful validation.
3. Add a scrollable segment list with index, role, text summary and after-pause. A selected-segment editor edits dialogue, speaker, pause, speed override and note. The speaker dropdown contains every declared `Role (id)` choice.
4. Add a scrollable role list with a selected-role editor: role/ID, voice selector, origin, locale/model status, note, effective settings, Preview and Reset. Avoid creating thousands of full widget rows for the 1,000-role bound. Keep stable source IDs as identity keys; role-label edits do not rename IDs implicitly.
5. Keep global provider/locale/search/model-library controls. Restore per-role choices on provider switches. Keep selected IDs when a search hides them. Edge remains editable text; local choices remain catalog selections with model guidance.
6. Display preflight counts, silence total and validation/warning summary. Selecting a diagnostic focuses its role/segment. Explain shared voices and note-only directions. Explicit unsupported settings block generation with actionable field errors.
7. Implement JSON Save As through the M12 serializer, dirty state and unsaved-change handling before replace/close. Preserve unknown extensions and never alter an imported file implicitly. If a raw JSON editor is added, require Validate/Apply before form state changes; it is optional, not a second independent source of truth.
8. Keep plain-text conversion explicit and label loss of JSON-only timing/directions/settings. It is acceptable to defer the conversion action rather than provide a lossy implicit mode switch. Plain-text mode remains directly usable.
9. Use weighted layout/split panes and compact stacked/tabbed arrangement when narrow. Keep editor/list scrollbars, consistent spacing/native theme/system fonts, clear focus and text-based status. Keep action/status controls reachable at small effective resolutions.
10. Collapse advanced export controls while preserving WAV/MP3/M4A, bitrate, normalization, sample/channel settings, output browse/open and overwrite behavior. Preserve Generate/Cancel/Replay/Stop and elapsed/stage progress.
11. Keep large-file read/parse, asset verification, synthesis and FFmpeg off the main thread. Capture immutable snapshots on the main thread; use queued revision-tagged import/preview/generation results. Reject stale results. Debounce filtering and validation; cancel/close must coordinate worker cleanup.
12. Extend preview to use the selected role's actual selected segment or first available dialogue and effective supported speed. Never speak JSON, labels or notes. Preserve the bounded cache; long explicit pauses may be omitted with a visible “speech only” label. Do not automatically synthesize on load/change.
13. Release obsolete widget traces/bindings when role views change. Maintain explicit app states for idle/importing/previewing/generating/cancelling/closing and consistent enabled controls.

## Required acceptance

- Import the unchanged sample: three role assignments, all three speaker options and 26 ordered segments are visible; 84 seconds of silence and final 30 seconds are shown.
- Manual role changes apply to all its segments. Reorder/filter/provider switches do not move assignments between roles.
- Invalid import preserves prior document, mappings and unsaved state. A stale import/preview cannot overwrite a newer revision.
- JSON form edits validate/save/reopen correctly; note and extension fields survive. Unsaved-close/replace choices work without hidden source overwrites.
- Generation captures a consistent snapshot; no background thread calls Tk widgets. Cancel and graceful close remain responsive with fake delayed providers/processes.
- Preview requests use the right dialogue/voice/effective setting, invalidate correctly and require an explicit user action.
- One-, three-, twenty-role and large-role cases remain navigable. Test long labels/IDs and all controls by keyboard.
- At 1024×768 with 100%, 150% and 200% Windows scaling, controls remain accessible by responsive layout or scrolling. Record actual environment/scaling evidence and gaps; do not equate a fake screenshot with OS scaling verification.
- Plain-text defaults, manual Edge IDs, model-library access, export options and overwrite safety remain usable.

## Verification and completion

Use injected provider/catalog/model sources for Tkinter acceptance; no real voice preview or model download. Cover queued states, dirty flows, role replacement, cancellation, stale revisions, resize and widget cleanup. Add a small layout/accessibility checklist and actual Windows observations. Do not add screenshot-golden tests that merely mirror widget implementation. Record M15 evidence and unresolved scaling/UI gates rather than inventing completion.


## Implementation and gate evidence — 2026-10-26

Status: **BLOCKED**. Structured desktop implementation is present and native
fake-provider checks pass. Open/import, separate Plain text/JSON sources, dynamic
role/segment editors, validation navigation, JSON Save As, dirty prompts,
collapsible exports, scroll/focus layout, revision-safe worker snapshots and
speech-only preview use the shared document/resolver/service. Source IDs and
unknown extensions are preserved. Legacy provider/model/export/preview controls
remain. Required actual 150%/200% OS scaling and keyboard checks are unavailable;
the host reports DPI96/100%, 1920×1080, with a 1024×768 test window. A Settings
launch returned "Computer Use app approval timed out"; no OS settings changed.
Do not mark DONE from passing Tk scaling emulation or existing files.

Full commands, environment, changed scope, traceability, prior corrected failures,
Ruff/manual review, exclusions and remaining gate checklist are recorded in
[M13–M17 verification](M13_M17_VERIFICATION.md). The explicit 31-file allowlist
passes **457 tests in 37.25 seconds** without skips/failures. All 14 changed Python
files pass Ruff and manual readability/privacy/architecture review; repository
findings are recorded separately. Failure, cancellation and cleanup tests pass.
No downloads, real inference, live synthesis, listening/comparison, benchmarks,
M11 rerun, package rebuild, dependency install, commit, push or release.
M10's historical BLOCKED status is unchanged.
