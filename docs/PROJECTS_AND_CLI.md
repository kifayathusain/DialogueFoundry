# Projects, presets and JSON CLI

These are explicit, data-only version-one formats. No file can execute a command,
supply a model URL or cause an automatic download. Only the chosen provider is
used for a job. Source paths in projects are provenance and are never fetched.

## Saved projects

**Save project As** writes a .ttsproject.json file containing:

| Field | Meaning |
| --- | --- |
| schema_version | Integer 1 |
| project_id | Stable identity for this saved project |
| document_id, revision | Active document identity and independent edit revision |
| document | Validated embedded source snapshot, including extensions |
| provider_id | edge, piper or kokoro |
| assignments | Provider ID → declared speaker ID → stable voice ID |
| locale, speed | Chosen metadata locale and optional job-speed override |
| export_settings | Shared ExportSettings fields for codec/rate/channels/normalization |
| text_settings | Shared TextProcessingSettings fields |
| source | Optional locator and SHA-256 content fingerprint for provenance |

The complete project is bounded to 16 MiB of UTF-8 JSON, with duplicate keys,
nonfinite numbers and excessive nesting rejected before recursive conversion.
An embedded document retains its 10 MiB, 64-container-depth and count limits.
The envelope permits one additional container level. Settings types and ranges,
provider IDs, declared mapping IDs and project version are validated before
adoption. Invalid explicit voice selections are kept visibly unresolved for
correction; unknown/removed speaker IDs are rejected. Opening a project clears
prior active edits before restoring its explicit assignments, even if a file
contains an identity that matches the active document.

**Open project** restores the embedded snapshot, all saved provider assignments
and processing/export choices. It does not re-read the source locator, so moved
or changed source files cannot silently replace saved work. No source-change
probe is currently performed. Asset readiness is rechecked using metadata hints
and then fully verified in the generation/preview worker.

Saves use a same-directory temporary file, flush/fsync, atomic replacement and
failure cleanup. The parent directory must exist. Projects contain private user
dialogue and settings deliberately; default job metadata contains hashes instead.
**JSON Save As** exports source JSON only; use a project to retain active mappings.
Saving a preset never changes source voice_defaults or a saved project implicitly.

## Reusable mapping presets

**Save mapping preset** captures the current provider's resolved role voices.
**Apply preset** explicitly enables the selected file's preferences for this
active document. No preferences file is automatically searched or enabled.
Matching uses the exact stripped, casefolded display role, provider ID and chosen
locale string. There is no gender, emotion, semantic or acoustic inference.
If multiple roles have the same normalized label, a preset has one entry for that
label/provider/locale; use explicit project assignments for distinct role IDs.

```json
{
  "schema_version": 1,
  "preferences": [
    {"role": "narrator", "provider_id": "edge", "locale": "en-US",
     "voice_id": "en-GB-SoniaNeural"}
  ]
}
```

At most 3,000 preferences are accepted. Duplicate normalized match keys fail.
Invalid metadata voice hints warn and fall through. Manual and explicitly loaded
project assignments take precedence, followed by imported provider defaults,
enabled preferences and deterministic catalog defaults. Reset voice clears the
selected manual/project override without touching other roles. Presets store
stable IDs, not display names, model paths or download locations.

## CLI

The no-argument `python main.py`, callable `main.main()`, configured
`conversation.txt` defaults, original output locations and legacy overwrite
behavior remain unchanged. `gen_audio.py` is unchanged and remains the legacy
per-line MP3 recombination helper; it does not reconstruct structured timelines.

Explicit arguments add:

```text
--input PATH
--input-format {auto,text,json}
--provider {edge,piper,kokoro}
--voice-map PATH
--output PATH
--overwrite
--speed NUMBER
```

Auto format uses .json for JSON, otherwise text. Explicit text/json overrides
the extension; malformed JSON never silently becomes text. New explicit exports
require WAV/MP3/M4A output extensions and refuse replacement without --overwrite.
--speed uses shared 0.5–2.0 validation and provider capability checks. Explicit
Edge speed is unsupported. CLI sessions close in finally on success, failure
or interruption, and validation errors return nonzero without a default traceback.

Example commands (these perform real synthesis only when a user runs them):

```powershell
python main.py --input docs/tts-sample.json --output sample.wav
python main.py --input dialogue.json --provider piper --voice-map piper-voices.json --output dialogue.m4a
python main.py --input dialogue.json --voice-map edge-voices.json --output dialogue.mp3 --overwrite
```

A voice map is intentionally smaller than a project:

```json
{
  "schema_version": 1,
  "provider_id": "edge",
  "voices": {
    "narrator": "en-GB-SoniaNeural",
    "clerk": "en-GB-RyanNeural",
    "customer": "en-GB-SoniaNeural"
  }
}
```

Omitted IDs use the shared deterministic resolver. The example shares a voice
and cannot promise three distinct deliveries. Custom nonempty Edge IDs remain
accepted. Piper IDs retain their full identity, for example
en_GB-vctk-medium:speaker_108; model IDs and numeric speakers are not role IDs.
An explicit --provider must agree with the map; unknown role IDs, malformed
types and invalid explicit local voices fail before synthesis. Required missing
or corrupt local models produce Model library guidance and no automatic download.

## Acceptance scope

Persistence, CLI and end-to-end behavior pass audited fake-provider and synthetic
media checks. M16/M17 remain BLOCKED by M15's missing 150%/200% OS scaling evidence.
No new voice-quality, real-model, benchmark, packaging or clean-machine acceptance
is claimed. See [the evidence report](milestones/M13_M17_VERIFICATION.md).
