# M13–M17 verification report — 2026-10-26

## Status and boundary

| Milestone | Status | Gate |
| --- | --- | --- |
| M13 | DONE | Pure mapping/settings acceptance passed |
| M14 | DONE | Fake-provider/exact PCM/synthetic export acceptance passed |
| M15 | BLOCKED | Implemented and native 100% UI checks pass; required actual 150%/200% OS scaling evidence missing |
| M16 | BLOCKED | Independent persistence/CLI and integrated snapshot tests pass; M15 dependency gate remains open |
| M17 | BLOCKED | Integrated offline acceptance/documentation implemented; M15/M16 gates remain open |

M12 work/evidence is preserved. M01–M09/M11 retain DONE; M10 retains its historical
BLOCKED status for actual clean Windows 11 installation evidence. No dependency
or OS scaling gate is waived by implementing/testing independent downstream work.

The user explicitly authorized M13–M17 in this session and requested automatic
sequential continuation. M13 passed before M14, and M14 passed before M15.
After the M15 environment gap was established, independent persistence/CLI,
snapshot integration, compatibility and documentation work continued under the
user's explicit blocker instruction; downstream DONE transitions are withheld.

No downloads, live Edge synthesis, real-model inference, quality/comparison/
listening work, provider benchmarks, M11 voice reruns, package rebuild, dependency
installation, public release, commit or push occurred. Existing user models,
catalogs, audio, legacy workflows and unrelated files are preserved.

## Environment and audited command

Windows 11 development host; CPython 3.13.17; pytest 9.1.1; Ruff 0.17.2;
existing FFmpeg/FFprobe 9.0.2 essentials. No tools were installed. Python 3.10
syntax parsing passes all 14 changed/new Python files; a Python 3.10 interpreter
runtime was not exercised.

[The explicit 31-file allowlist](M13_M17_OFFLINE_TESTS.txt) extends the existing
M12 allowlist with five reviewed test modules. Existing allowlisted files and
their external boundaries were reviewed against M12's audit and current source.
There are no conftest files. Third-party plugin autoload is disabled; no ambient
TTS/model opt-ins were used. Provider runtime/Edge tests inject fake adapters;
model-manager transactions use tiny temporary in-memory responses, never real
downloads. Subprocess lifecycle tests start controlled Python children. Synthetic
FFmpeg fixtures contain programmatic sine/DC/zero PCM or encoded copies, never
provider speech. The native UI module uses FakeSource and SilentPlayer, with one
Tk interpreter matching the production lifetime. Its imported helper modules
define no import-time inference, downloads or windows.

From the repository root:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:TTS_FFMPEG_TESTS='1'
$env:TTS_EXPORT_TESTS='1'
$env:PATH=(Resolve-Path .venv-backup/ffmpeg-toolset).Path+[IO.Path]::PathSeparator+$env:PATH
$env:TCL_LIBRARY=(Resolve-Path .venv-backup/python313-official/tcl/tcl8.6).Path
$env:TK_LIBRARY=(Resolve-Path .venv-backup/python313-official/tcl/tk8.6).Path
$auditedTests=Get-Content docs/milestones/M13_M17_OFFLINE_TESTS.txt
.\.venv-backup\python313-official\python.exe -m pytest @auditedTests -q --basetemp=.venv/m13-m17-verified -o cache_dir=.venv/m13-m17-cache --tb=short
```

Execution outside the sandbox permits Windows asyncio's local socket pair.
The initial sandbox attempt stalled at an existing asyncio case and was stopped.
No marker-only full-suite command was used.

## Acceptance traceability

Test files below are under tests/.

| Requirement | Evidence |
| --- | --- |
| Original sample | test_conversation_document; test_speaker_mapping; test_structured_generation::test_sample_exact_pauses_and_only_dialogue; test_structured_gui::test_end_to_end_sample_gui_export_project_and_cli |
| Arbitrary roles | test_structured_gui parameterized 1/3/20/1000 list/form navigation; long-label and 305-character-ID reload case |
| Stable identity/defaults | test_speaker_mapping precedence, locale/presence/unused ties, reorder/delete/reconcile/provider/reset; test_structured_gui provider restoration/filter retention |
| Distinctness limitations | Sample shared-Edge diagnostics; custom Edge assignment and full Piper ID CLI tests |
| Directions/speed | Pure precedence/invalid-speed matrix; per-chunk speed/span test; visible note-only GUI status; no notes/labels in fake requests |
| Timing | 26 after-pause timeline items, exact 84 × 16000 zero frames and final 30 seconds; zero/sub-frame/fractional/600-second cases; independent intra-segment sentence pauses |
| Export | Synthetic WAV/MP3/M4A with/without normalization and final zero samples; existing synthetic mixed-layout/native MP3/overwrite/timeout integrations |
| Validation | M12's 148 document cases plus mapping/service validation-before-job tests; shared bounded decoder retained |
| Safe state | Failed/stale JSON import, invalid project adoption, unsaved choices, pending editor retention, same-ID project reopening and stale preview/generation tests |
| GUI | Actual Windows Tk at reported 100%/DPI96, 1024×768 and narrow 512×384; keyboard tree/focus scrolling and dynamic controls pass. Actual 150%/200% and all-controls keyboard review at those OS scales remain UNVERIFIED |
| Cancellation | Fake inference, blocking decode/silence/export task cancellation, subprocess timeout/reaping, native queued cancel and graceful-close cleanup |
| Preview | Actual selected-role dialogue/effective speed, speech-only label, explicit action, stale result rejection and retained preview-cache regressions |
| Projects/presets | Bounded versioned snapshots, moved/inert source provenance, all-provider mappings/settings/locale, invalid types/version/IDs, duplicate keys/depth/size, fsync/replace failure cleanup and manual-preserving exact preferences |
| CLI | Shared-service snapshot/timeline parity, custom Edge/full Piper IDs, provider mismatch/unknown role/invalid local mapping rejection before acquisition, overwrite protection, failure/interruption session cleanup and nonzero concise errors |
| Legacy | Audited parser/service/provider/GUI/export/session regressions; main.main no-argument compatibility; gen_audio.py unchanged |
| Verification safety | Explicit allowlist and exclusions below; no prohibited provider activities |

Unchanged sample SHA-256:
81e9d951bdd041e6e6b6dd487e928b85cd97abbde09a666280fe3019243a2dc8.
The integrated GUI exports the unchanged sample before editing its final pause to
30.125, saving/reopening a project and generating equivalent CLI input. The edited
timeline then totals 84.125 seconds; this does not change the bundled fixture.

## Failures investigated and corrected

- M14's first normalization fixture used nearly silent DC PCM and was correctly
  rejected as unmeasurable. Media-only tests now use a measurable non-speech tone;
  exporter validation was preserved.
- Native GUI tests initially created multiple Tk roots and intermittently failed
  reading existing Tcl resources. They now use one interpreter/window for the
  desktop lifetime and explicit existing Tcl/Tk resource paths; no runtime files
  were installed/replaced. Initial focus checks were corrected to obtain native
  focus before keyboard checks.
- E2E tests initially assumed an output folder and role selection instead of
  using the existing audio_parts path and explicitly selecting the intended role.
  These test setup errors were corrected; the emitted requests exposed the
  mistaken assumptions.
- A pre-existing atomic metadata publication path intermittently raised Windows
  access-denied during rapid updates (observed in a legacy regression; a later
  native GUI run failed during metadata progression and passed in isolation).
  M17 adds bounded 10/30/100 ms retries for Windows access/sharing/lock errors only.
  Permanent failures still propagate, clean temporary metadata and preserve prior
  final output. Controlled transient/permanent failure tests cover this fix.
  The metadata representation also uses typed segment records and includes an
  explicit assignment hash. No final-audio publication rules were relaxed.

Intermediate completed broad runs passed 379 (M13), 403 (M14), 452 and 455 checks
before the final two metadata fault-injection cases. Intermediate failed runs
are not counted as passing totals. The final result is recorded below.

## Ruff, compatibility and manual review

Changed-file commands use
.venv-backup/quality-tools/bin/ruff.exe format --check and check with these paths:

```text
ttsapp/speaker_mapping.py ttsapp/service.py ttsapp/generation.py ttsapp/gui.py
ttsapp/structured_editor.py ttsapp/conversation_document.py ttsapp/project_storage.py
ttsapp/cli.py main.py tests/test_speaker_mapping.py tests/test_structured_generation.py
tests/test_structured_gui.py tests/test_project_storage.py tests/test_json_cli.py
```

Repository commands: ruff.exe format --check . --output-format concise and
ruff.exe check . --output-format concise. No repository-wide autoformat/fix ran.
Changing main.py for the additive CLI also resolved its previous I001/format
finding within scope. Remaining pre-existing findings:

| File | Finding |
| --- | --- |
| tests/test_parser.py:1 | I001 |
| gen_audio.py | Ruff formatting difference |
| tests/test_audio_combiner.py | Ruff formatting difference |
| tests/test_parser.py | Ruff formatting difference |
| tests/test_tts_engine.py | Ruff formatting difference |

Manual review confirms descriptive names, focused typed document/mapping/storage/
provider/audio boundaries, additive public service inputs, stable IDs, explicit
errors/control flow, suitable docstrings, no compressed statements/suppressions,
private dialogue/notes excluded from job metadata and no optional runtime import
or provider capability expansion. Tk mutations remain on the main thread; workers
consume snapshots and queue revision-tagged results. Atomic save and job cleanup
paths are covered. Packaging resources were not changed: runtime operation does
not load the new user guides/schema/examples, so no rebuild was necessary.

## Explicit exclusions, not failures

| Excluded files under tests/ | Reason |
| --- | --- |
| test_piper_integration.py, test_kokoro_integration.py, test_preview_integration.py, test_longform_integration.py | Real inference prohibited |
| test_model_manager_integration.py, test_windows_package_integration.py | Real download/model/package acceptance can trigger prohibited work |
| test_gui_integration.py, test_gui_export_integration.py, test_english_voices_integration.py | Historical real-provider Windows acceptance; replaced for new behavior by injected fake-provider UI checks |
| test_diagnostics.py | Diagnostic/build acceptance outside reviewed safe boundary; can invoke providers |
| test_voice_validation_report.py, test_voice_catalog_updater.py, test_english_catalog.py | Separate voice-validation/catalog-maintenance scope; no exhaustive M11 rerun |
| test_model_library.py | Outside retained audit allowlist; model-library boundaries retained through fake manager/provider regressions |

No exclusion is reported as a pass. The unavailable 150%/200% OS scaling checks
are required missing evidence, not prohibited tests. A Computer Use attempt to
launch existing Windows Settings returned "Computer Use app approval timed out";
no settings were changed and no synthetic Tk scaling was substituted for OS
evidence. The actual saved host report is DPI96/100%, 1920×1080 screen,
1024×768 window and Tk scaling 1.3333333333333333. Python 3.10 runtime and clean
Windows 11 packaging acceptance are not claimed.

## Remaining completion gate

- [x] M13 and M14 acceptance passed before successor implementation.
- [x] Independent M15/M16 behaviors and integrated safe regressions pass.
- [x] Changed-file Ruff and manual architecture/readability review pass.
- [x] Repository-wide Ruff findings and explicit exclusions are separate.
- [x] Failure/cancellation/cleanup and compatibility evidence is recorded.
- [x] User guides, architecture and milestone evidence describe implemented behavior.
- [ ] Required actual 150%/200% Windows UI/scaling and associated keyboard review.
- [ ] M15 DONE, then M16 dependency gate, then M17 final DONE.

No automatic commit, push, release or historical milestone waiver.

Final broad outcome: **457 passed in 37.25 seconds**, no skips/failures.
Changed-file Ruff: **14 already formatted; all checks passed**. Repository checks:
**one pre-existing I001 and four pre-existing formatting differences**, as listed.
Git diff whitespace check passes; bundled sample hash and source diff remain unchanged.

Read-only OS scaling confirmation: Windows Shcore GetScaleFactorForMonitor on the
primary monitor returned HRESULT 0 and **100%**. GetProcessDpiAwareness returned
0 for the test interpreter, so window DPI alone could have been virtualized; the
independent monitor API confirms the current 100% OS setting. No display setting
was changed. Required 150%/200% runs remain unavailable.
