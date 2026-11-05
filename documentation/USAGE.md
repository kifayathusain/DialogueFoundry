# DialogueFoundry usage and examples

Run commands from the repository root in the environment installed in
[Getting started](GETTING_STARTED.md). The small [plain-text sample](../examples/hello.txt)
and [JSON sample](../examples/hello.conversation.json) contain fictional dialogue.

## Plain text and structured input

Plain text uses one `Speaker: text` turn per line. The CLI's default labels are
`Receptionist` and `Caller`, mapped to `en-GB-SoniaNeural` and `en-GB-RyanNeural`.
The desktop's legacy controls allow editing the two labels and voices. For more
roles use JSON, which declares speaker IDs and an ordered `segments` array.

```json
{
  "schema_version": 1,
  "speakers": [{"id": "narrator", "role": "Narrator"}],
  "segments": [{"speaker": "narrator", "text": "A fictional story begins.", "pause_after_seconds": 0.5}]
}
```

IDs are case-sensitive. Every segment must refer to a declared speaker. Optional
speaker fields include `gender`, `description`, `voice_direction`,
`voice_defaults` keyed by provider, and `speech: {"speed": 1.0}`. Segments may
also have `voice_direction` and `speech`. Direction text is guidance for review,
not a promise that a TTS engine implements emotional delivery.

The [schema](../examples/structured/tts-input.schema.json),
[optional-field example](../examples/structured/tts-input-example.json) and
[longer fictional repair-shop lesson](../examples/structured/tts-sample.json)
are included for contributors and parser examples. The longer lesson has 26 turns
and 84 seconds of explicit pauses, including a final 30 seconds; it is deliberately
slower than the hello quick start.

Explicit after-pauses, including zero and the last segment's pause, are preserved.
The parser accepts at most 10 MiB, 1,000 speakers and 10,000 segments, with bounded
nesting and pauses. Duplicate keys and nonfinite numbers are rejected. The desktop
validates edits before updating its working snapshot. It can export source JSON,
save `.ttsproject.json` with embedded dialogue/mappings/settings, and explicitly
apply role-mapping presets. Projects contain your script; protect them accordingly.

## Voice maps and exports

Use the [Edge map](../examples/hello.edge-voices.json) or
[Kokoro map](../examples/hello.kokoro-voices.json):

```powershell
.\.venv\Scripts\python.exe main.py --input examples/hello.conversation.json --provider edge --voice-map examples/hello.edge-voices.json --output dialogue.m4a
```

The map has `schema_version: 1`, `provider_id` and `voices` mapping declared speaker
IDs to exact voice IDs. An explicit `--provider` must agree with the map. Missing
IDs use deterministic defaults; missing local assets cause an error. Provider/model
IDs are distinct from speaker IDs. Piper multi-speaker voice IDs include the
speaker suffix, such as `en_GB-vctk-medium:speaker_108`.

Manual assignments and loaded project assignments take precedence over source
voice defaults, enabled role preferences and catalog defaults. Filtering a desktop
list does not change mappings. Use preview/replay/stop to audition, then Generate.
Workers report progress and support cooperative cancellation. New explicit CLI
exports refuse replacement unless `--overwrite` is supplied. Choose WAV, MP3 or
M4A by output extension; advanced layout and normalization controls are in the
desktop and Director direction files.

No-argument `main.py` and `gen_audio.py` retain legacy behavior. The latter combines
existing per-line MP3s; it does not reconstruct structured pauses or Director plans.

## Audio Director

Open **Audio Director…** in the desktop. Select source/output folders, scan,
choose a provider and leave **Use AI planner** off for manual operation. Review
casts, destinations, timing and scene settings, audition Original/Directed, then
generate. Invalid files are reported; continue/stop policy controls batch failures.
Explicitly link a recurring speaker across selected files rather than relying on
equal role labels. Replace, rename or skip output conflicts before rendering.

Optional AI planning needs an available OpenAI-compatible JSON-mode local server
or the app's OpenAI configuration, a model ID and applicable credentials. Cloud
planning requires explicit consent and offline mode disabled. Review proposals
before rendering. Neither the app nor the planner installs an LLM. Full dialogue
sharing is a separate opt-in. See [Privacy](PRIVACY.md).

The tracked [mixed conversation](../examples/audio_director/mixed.conversation.json)
and [direction](../examples/audio_director/mixed.direction.json) demonstrate a
fictional telephone exchange. `Lessons/04_malformed.json` under the same example
folder is **intentionally invalid** (an undeclared speaker), for error
demonstrations; exclude it from a batch intended to succeed fully. Direction files
are settings, not conversation inputs.

For the mixed example, install both local runtimes, `kokoro-82m-v1` and
`piper-lessac-low` first. Review Lessac's unresolved terms before use:

```powershell
.\.venv\Scripts\python.exe main.py director discover --offline
.\.venv\Scripts\python.exe main.py director validate --input examples/audio_director/mixed.conversation.json --direction examples/audio_director/mixed.direction.json --output mixed.wav --plan mixed.plan.json
.\.venv\Scripts\python.exe main.py director render --plan mixed.plan.json
```

Discovery verifies local asset state but does not prove synthesis or Edge
availability. Validation writes a **new** plan file and checks prerequisites.
Inspect its resolved cast, pauses, effects and licensing before rendering. Changes
to source/direction require a fresh plan. Validation/render make no LLM call.

Director `settings.voices` accepts exact `{ "provider": "kokoro", "voice":
"bm_george" }` objects per speaker or legacy voice strings using the default
provider. Required `speaker_preferences` locale/language constraints reject
mismatches; descriptive qualities remain listening judgments. `offline: true`
excludes Edge. Phone effects apply only to the selected speaker within inclusive
one-based turn ranges. Mixed audio uses common 24 kHz mono 16-bit PCM before
effects/assembly and final export settings. The plan and reports can contain paths;
sanitize before sharing them.
