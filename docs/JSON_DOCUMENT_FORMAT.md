# Structured conversation JSON (version 1)

The document API in `ttsapp.conversation_document` is shared by desktop import,
voice mapping, structured generation and the JSON CLI. Existing `Speaker: text`
input is unchanged. Desktop acceptance still awaits 150%/200% OS scaling checks;
see the milestone tracker. See the [sample](tts-sample.json),
[optional-field example](tts-input-example.json) and
[JSON Schema](tts-input.schema.json).

The root object requires nonempty `speakers` and `segments` arrays. Omitted
`schema_version` means integer 1. Each speaker requires a unique, case-sensitive
`id` and nonblank `role`. Duplicate display roles are allowed. Each segment
requires a declared `speaker` ID and nonblank `text`. IDs must already be trimmed;
references are never rewritten. Original role labels, text, punctuation, colons,
newlines and Unicode remain intact.

Speakers and segments accept optional string `voice_direction` notes (default
empty) and `speech` objects with optional numeric `speed` (default unset).
Speakers also accept `voice_defaults`, an object mapping trimmed provider IDs to
trimmed voice IDs. M12 validates their shape without resolving providers or
checking models. Directions are preserved notes; they do not control synthesis.
Effective speed precedence is segment > role > job > provider default.
Explicit Edge speed is unsupported and is rejected by generation
preflight. Importing this example does not synthesize anything.

Segments accept `pause_after_seconds`, default zero, including fractional values
and the final segment's pause. Structured generation renders these as exact PCM silence,
including the final after-pause, using round(sample_rate × seconds) frames. Existing five-second sentence/paragraph settings
are separate and unchanged.

Audio Director adds an opt-in natural-timing plan setting without changing this
version-one contract. It inspects the retained source tree: omission permits a
bounded automatic gap at a nonfinal speaker change; an explicit zero forbids one.
Explicit positive and final pauses remain exact. Plain structured rendering still
defaults omitted pauses to zero. See [Audio Director](setup/AUDIO_DIRECTOR.md).

Limits are centralized in the document module:

| Limit | Value |
| --- | --- |
| Input | 10 MiB UTF-8, including BOM/whitespace in serialized input |
| Speakers / segments | 1–1,000 / 1–10,000 |
| Explicit after-pause | 0–600 seconds |
| Total explicit silence | At most 86,400 seconds |
| Explicit speed | 0.5–2.0 |
| Container depth | 64, counting the root object as 1 |
| Diagnostics | First 100 errors, then one `diagnostics_omitted` sentinel; warnings independently bounded the same way |

Booleans, numeric strings, null and non-finite numbers are invalid for numeric
fields. Optional fields are validated when present; null never means omitted.
Unknown fields at any supported object level are retained and warned about;
nested extension payloads remain intact and must also contain valid finite JSON.
Duplicate keys at every depth are errors, including escaped spellings of the
same key. JSON Schema documents structural constraints; the Python validator
also enforces references, unique IDs, duplicate keys, cumulative silence,
finite numbers, byte size and depth. JSON Schema treats `1.0` as an integer;
the runtime deliberately requires the schema version to be a Python/JSON integer
token and rejects `1.0` as well as `true`.

## Python API

```python
from pathlib import Path
from ttsapp.conversation_document import load_document, save_document_as

document = load_document(Path("docs/tts-sample.json"))
edited_source = document.to_dict()
edited_source["segments"][0]["text"] = "Updated dialogue"
edited = document.with_data(edited_source)
save_document_as(edited, Path("conversation-copy.json"))
```

`parse_document_text(str_or_bytes)` accepts UTF-8 with an optional BOM.
`parse_document_data(tree)` accepts only JSON-compatible Python dict/list trees;
its equivalent byte limit uses compact unescaped UTF-8 JSON. Both apply the same
semantic validator as `load_document`. Depth is checked iteratively before
recursive decoding/encoding, respecting quoted braces and escaped quotes.
`DocumentValidationError.diagnostics` contains stable codes, semantic paths and
messages. Syntax errors additionally include line and column. No default logs
or exception messages dump dialogue text. `DocumentIOError` reports file errors.

Parsed core records are frozen and voice defaults are read-only. `to_dict`
returns an isolated copy including extension payloads. `serialize_document`
returns the validated source JSON without a BOM, preserving source values,
field absence and formatting. Python-tree input uses compact unescaped JSON.
Retaining the source also prevents number reformatting from expanding a valid
document beyond the byte limit when it is saved. Saving uses
a temporary file beside the explicit destination, flush/fsync and atomic replace,
with temporary-file cleanup on failure. The destination parent must exist.
Importing never implicitly writes to its source. These synchronous document
operations do not have a cancellation contract or initialize providers/models.

Every new import receives a fresh `document_id`, initially revision 0. Content
hashes use sorted-key compact UTF-8 JSON and exclude active identity/revision.
`document.with_data(tree)` validates an edit, retains identity and advances the
revision; invalid edits leave the old snapshot intact. Explicit
`load_document(path, reload_of=active)` (or either parse function's `reload_of`)
retains active identity and advances revision. Only pass `reload_of` when the
caller intentionally reloads the same active source. Desktop imports start fresh;
explicit project opening restores its saved identity/revision and assignments.


## Mapping and generation

Assignment precedence is current edit > explicitly opened matching project >
valid imported provider default > enabled exact role/provider/locale preset >
deterministic catalog default. Defaults rank locale, file-presence hint, unused
voice and stable catalog order. Presence is not integrity verification. Every
declared role receives a voice; only used roles need ready assets. Shared IDs
are warned about and do not guarantee distinct delivery. Custom nonempty Edge
IDs remain editable; local IDs must match the catalog, including full Piper
model/speaker IDs. Import/filtering never loads weights or discovers voices online.

Free-text directions remain visible notes, never guessed speed/pitch/emotion.
Only dialogue chunks reach synthesis. Supported speed resolves segment > role >
job > provider default. An untouched disabled Edge job-speed display is not an
explicit request. Role/segment speed overrides still fail for Edge.

Each segment is chunked independently with normalized source spans. Optional
sentence silence occurs only inside its segment. JSON paragraph whitespace adds
no boundary pause; every explicit after-pause occurs once after its last chunk,
including final silence. Provider natural silence is retained. Sub-frame pauses
rounding to zero create no file. Legacy sentence/paragraph bounds stay at five
seconds. The unchanged sample has 3 roles, 26 segments and 84 seconds of explicit
silence, including its final 30 seconds.

The additive service inputs are `document=ConversationDocument` and
`voice_assignments={speaker_id: stable_voice_id}`. A document cannot accompany
`input_text` or a nondefault explicit file source. File callers explicitly choose
the document parser or legacy parser; the service does not guess file format.
Structured calls always use processed generation, including native Edge MP3
decoding. Existing legacy unprocessed Edge stream-copy behavior is preserved.
Version-2 `generation.json` records identity/revision, selected voices, effective
settings, source hashes, ordered speech/silence states and request hashes.
It contains no private dialogue or direction-note bodies and does not resume
or reuse previous chunks. See [projects/CLI](PROJECTS_AND_CLI.md).
