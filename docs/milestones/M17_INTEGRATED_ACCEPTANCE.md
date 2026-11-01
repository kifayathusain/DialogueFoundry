# M17 — Integrated acceptance, compatibility and documentation

Initial status: NOT_STARTED. Dependency: M16 DONE. Read shared rules before editing.

## Objective

Verify the complete JSON workflow and publish accurate setup/usage/evidence documentation without repeating voice testing or claiming unresolved packaging gates passed.

## Implementation and review tasks

1. Walk the full scenario with fake providers: import unchanged sample, inspect all roles, modify assignments/settings, edit a pause, generate, cancel, save/reopen a project and invoke equivalent CLI input. Verify state and emitted requests/timeline, not just widget presence.
2. Complete the traceability matrix below with links to actual tests/manual evidence. Fix only relevant integration defects. No unrelated refactoring or new features.
3. Run the audited broad regression set, synthetic FFmpeg integrations and fake-provider Windows UI acceptance. Explicitly record prohibited/unavailable test exclusions and separate pre-existing failures from introduced failures. No live provider/model/benchmark/quality checks.
4. Run Ruff for changed Python files and repository-wide checks; leave unrelated old findings documented. Review readability, type hints, cleanup, privacy and architecture manually.
5. Update README's outdated two-voice/Edge-only description, JSON format/schema guide, mapping/default/direction limitations, pause semantics, GUI guide, project/preset guide and CLI examples. Keep historical evidence intact.
6. Update `ARCHITECTURE.md`, master plan and tracker with final implemented behavior, interfaces, test commands and limitations. Add the new docs/schema/examples to existing packaging data only if the current package needs those runtime resources. Do not rebuild/distribute a package or run package diagnostics that trigger voice checks as part of this milestone.
7. Verify service entry points and public compatibility from observable tests. Review new imports for unwanted optional-runtime loads and new dependencies. Do not claim all provider audio is revalidated.

## Final traceability matrix

| Requirement | Acceptance evidence |
| --- | --- |
| Original JSON sample | Three roles, 26 segments, 84-second explicit silence, final 30 seconds retained |
| Arbitrary declared roles | Every role gets a populated editable assignment; all declared roles appear in segment dropdowns; large lists stay usable |
| Stable defaults | Manual/project/imported/preference/catalog precedence, filtering and provider restoration |
| Distinctness limitations | Two default Edge IDs shared across three roles produce an honest warning; manual IDs remain accepted |
| Direction handling | Only dialogue reaches synthesis; notes/status are visible; supported speed propagates; unsupported explicit controls fail |
| Exact timing | Final and multi-chunk pauses, zero/fractional/long silence, no duplicate paragraph gaps, frame-count proof |
| Export behavior | Synthetic WAV/MP3/M4A, normalization/layout handling, trailing silence and duration tolerance |
| Validation | Duplicate keys/IDs, unknown references, wrong types, boolean numeric values, nonfinite values, depth/size/count limits and unsupported versions |
| Safe state changes | Failed import/save/load and stale workers preserve the correct document and assignments |
| GUI | Keyboard flow, 1/3/20/large-role cases, resizing, long labels, actual Windows scaling checks |
| Cancellation | Inference fakes, decode/export subprocesses, silence writer and close/worker cleanup |
| Preview | Selected-role dialogue/settings only, speech-only pause labeling, cache/revision invalidation, explicit user action |
| Project/preset | Round-trip snapshot, provider assignments, stable identities, opt-in preferences and no silent override |
| CLI | JSON/shared service parity, invalid map/provider failure, overwrite safety and legacy no-argument behavior |
| Legacy compatibility | Text parser, Edge fast path, local dispatch, catalogs/model library, original entry points and callbacks |
| Safety of verification | No downloads, live synthesis, voice comparisons, benchmarks or M11 revalidation; exact exclusions listed |

## Completion criteria

- All applicable matrix rows have passing evidence. A missing required feature check is reported as unmet, never converted into a pass.
- M12–M16 evidence is complete and dependencies truly pass.
- Documentation describes supported behavior and limitations without suggesting free-text emotion/style is enforced or all assigned voices are necessarily distinct.
- Existing providers and FFmpeg remain intact; no models/audio binaries are added to Git.
- Historical milestone statuses remain unchanged; M10 remains BLOCKED. Feature acceptance does not imply a clean Windows 11 package acceptance or public release.
- Final report lists implementation outcome, exact verification scope/results, excluded checks, existing issues and any remaining feature limitations.

Do not extend M17 into deferred features, a quality campaign, model installation, signing or release work. If a required tool/environment check is unavailable, preserve the implemented work and record the specific unresolved gate.


## Implementation and gate evidence — 2026-10-26

Status: **BLOCKED** on M15/M16 completion gates. The full safe sample scenario,
compatibility checks, exact silence/export proof, project/reopen/CLI parity,
cancellation and documentation review are implemented and tested. A concrete
Windows atomic metadata sharing defect discovered in regression work has a short
bounded retry with transient/permanent failure tests. Typed metadata includes
assignment/request hashes and no dialogue/note bodies. Actual 150%/200% OS scaling
and corresponding keyboard review remain unverified; no clean-machine or
real-provider quality pass is inferred.

Full commands, environment, changed scope, traceability, prior corrected failures,
Ruff/manual review, exclusions and remaining gate checklist are recorded in
[M13–M17 verification](M13_M17_VERIFICATION.md). The explicit 31-file allowlist
passes **457 tests in 37.25 seconds** without skips/failures. All 14 changed Python
files pass Ruff and manual readability/privacy/architecture review; repository
findings are recorded separately. Failure, cancellation and cleanup tests pass.
No downloads, real inference, live synthesis, listening/comparison, benchmarks,
M11 rerun, package rebuild, dependency install, commit, push or release.
M10's historical BLOCKED status is unchanged.
