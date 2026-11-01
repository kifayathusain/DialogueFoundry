# M16 — Saved projects, reusable presets and JSON CLI

Initial status: NOT_STARTED. Dependency: M15 DONE. Read shared rules before editing.

## Objective

Let users reopen an edited conversation with its mappings/settings, reuse chosen defaults explicitly, and generate JSON through the CLI while preserving no-argument legacy behavior.

## Implementation tasks: project and presets

1. Add versioned explicit project Save/Open. Use a sidecar such as `.ttsproject.json` containing document identity, a validated document snapshot, source locator/hash for provenance, per-provider assignments and export/processing preferences. Embed the snapshot so reopening is reliable even if the source is moved; a changed source does not silently replace saved edits.
2. Distinguish project identity, current document revision and source content hash. Reload the saved snapshot and mappings; show original-source changes as informational status if checked. An unrelated document cannot inherit assignments just because speaker labels match.
3. Persist data only, never executable instructions, arbitrary model/download URLs, pickle objects or commands. Validate project version, source snapshot, provider/voice values, types and limits before changing app state. Source paths are provenance, not instructions to execute or auto-fetch. User-selected output paths go through normal overwrite/export checks.
4. Revalidate all loaded mappings. Preserve invalid explicit selections visibly for correction; do not replace them invisibly or download missing assets. A saved provider choice may restore the project's selection, visibly, without silently falling back to a different provider.
5. Use explicit atomic save transactions and dirty-state integration. Project files deliberately contain user dialogue/settings; default job diagnostics still contain hashes. Do not log project bodies. Apply a documented 16 MiB project-file bound plus the embedded document's original limits.
6. Add explicit Save mapping preset / Apply preset and opt-in reusable role/provider/locale defaults. Store stable voice IDs, not display labels or model paths. Version the format and validate imported files. Never read credentials or arbitrary unrelated folders.
7. Match reusable role preferences by exact normalized display role plus provider and chosen locale; no semantic/gender inference. Document this match rule. Project/speaker-ID assignments retain higher precedence.
8. Applying a preset defaults to unresolved/automatic roles only, leaving manual choices intact. Provide a clearly named explicit replace action if full replacement is useful. Reset unmapped roles does not reset edited valid roles.
9. Keep source JSON `voice_defaults`, reusable presets and active/project overrides distinct; saving one must not silently update the others.

## Implementation tasks: CLI

1. Add optional `--input`, `--input-format {auto,text,json}`, `--provider`, `--voice-map`, and `--output` arguments through the existing entry point, adapting names to current conventions if required. Preserve the callable/no-argument legacy `main` path and defaults.
2. Use a small mapping-file contract: `schema_version: 1`, a known `provider_id`, and `voices` mapping declared speaker IDs to stable voice IDs. It need not be a full project. Reject malformed keys, mismatched explicit provider, unknown speaker IDs and invalid explicit mappings before generation.
3. Omitted JSON mappings use the shared deterministic resolver; mapped IDs override those defaults for this invocation. Missing required local assets produce actionable nonzero failure without download. Unknown extension metadata must not trigger code or network execution.
4. Use the same document parser, resolver, validation, generation and export service as the GUI. Do not reimplement pause or direction behavior in argument handling.
5. Maintain existing defaults for `python main.py`: `conversation.txt`, configured legacy voices and original output paths/behavior. New explicit JSON export paths use the validated exporter and refuse replacement unless an explicit CLI overwrite option is set. Preserve legacy no-argument overwrite behavior rather than silently changing it.
6. Give actionable validation errors and nonzero exit status without default tracebacks or private dialogue dumps. Preserve progress, release provider sessions in `finally` and propagate cancellation/interruption through cleanup.

## Required acceptance

- Project Save/Open restores edited dialogue, timing, notes, all-provider mappings and export settings; moved sources do not lose work.
- Malformed/oversized/unsupported project files leave active state unchanged; failed atomic saves preserve existing files.
- Stable identities stop mappings leaking between projects/documents. Source fingerprints are not used as mutable row keys.
- Presets apply only under their documented policy, retain manual edits by default and identify missing/invalid voices without downloading.
- CLI JSON and GUI service snapshots produce equivalent resolved requests/timelines under fakes.
- Explicit mappings honor stable Piper IDs and custom Edge IDs; provider mismatch and unknown role mappings fail before synthesis.
- `python main.py` and existing direct callers preserve legacy behavior; `gen_audio.py` is unchanged.
- New JSON CLI overwrite/cancellation/failure paths protect existing final output and close sessions.

## Verification and completion

Use temporary project/preset files, fake providers and mocked CLI boundaries. Test malformed data, changed/missing source, identity collisions, overrides, atomic failures, interrupt cleanup and no-argument compatibility. Document schemas and CLI examples. Do not test the CLI by invoking real voices. Record M16 evidence.


## Implementation and gate evidence — 2026-10-26

Status: **BLOCKED** on M15's completion gate. Independent authorized implementation
and acceptance are present: bounded versioned atomic embedded projects, stable
identities/all-provider mappings/settings/locale, inert source provenance, opt-in
exact role/provider/locale presets, GUI Save/Open/Apply wiring, shared JSON CLI,
provider/map validation, overwrite safety and finally session cleanup.
The no-argument main.main/python main.py path and gen_audio.py remain compatible.
No project locator is read/fetched and invalid explicit selections stay visible.
Passing independent tests does not bypass M15's missing OS scaling evidence.

Full commands, environment, changed scope, traceability, prior corrected failures,
Ruff/manual review, exclusions and remaining gate checklist are recorded in
[M13–M17 verification](M13_M17_VERIFICATION.md). The explicit 31-file allowlist
passes **457 tests in 37.25 seconds** without skips/failures. All 14 changed Python
files pass Ruff and manual readability/privacy/architecture review; repository
findings are recorded separately. Failure, cancellation and cleanup tests pass.
No downloads, real inference, live synthesis, listening/comparison, benchmarks,
M11 rerun, package rebuild, dependency install, commit, push or release.
M10's historical BLOCKED status is unchanged.
