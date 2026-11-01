# Audio Director

Launch `python app.py` from the repository in your configured Python environment,
then choose **Audio Director…** above the text editor. The workspace is a modal
window in the existing desktop app. It keeps the older text, JSON, project and
CLI workflows intact. Python 3.10–3.13 is required for the optional Kokoro runtime.
FFmpeg **and FFprobe** must be on PATH for every validated Director export.

## Choose folders → Describe → Review or preview → Generate

1. Browse to the conversation folder and an output folder. Choose MP3, WAV or
   M4A, then **Scan folder**. Only the selected folder is scanned unless you
   enable **Include subfolders**. The list distinguishes invalid conversations
   from excluded projects, presets, reports and unrelated JSON. The Review tab
   lists exclusions. Limits: 200 JSON files, 64 MiB source data per scan, and the
   existing 10 MiB document limit. Input files are never rewritten.
2. Choose a default provider. **Fully offline** permits local providers only.
   Leave **Use AI planner** off for manual setup. Installed voices can render
   without an LLM. Open **Model library** to explicitly install/verify missing
   models; the Director never downloads or substitutes a provider automatically.
3. Enter a Direction, configure the LLM if using AI, then **Build plan**. This
   verifies required local assets in a worker. A source edit after scanning blocks
   its render and asks for a rescan. An invalid file can remain blocked while
   other files run under the **continue** failure policy.
4. Select a file. Review the provider, destination, speed, cast, exact after-pauses,
   acoustic settings and diagnostics. **Apply settings to** explicitly selects
   one file or the whole batch. Destination rename, Skip and Replace affect only
   the selected file, even during a batch settings edit. Duplicate base names
   across subfolders and occupied outputs block synthesis until renamed, skipped
   or explicitly replaced. Replacement does not resolve two batch files targeting
   the same name: rename or skip one.
5. In **Cast**, choose a source speaker and edit its stable voice ID. To bind a
   recurring character, first Ctrl/Shift-select its files, then choose the speaker
   in Cast and **Link this speaker ID across selected files**. All linked members
   must have that exact ID and use one provider. Differing IDs can be edited
   independently to the same voice. Equal role names never establish identity.
   Catalog defaults use unused voices where possible; finite inventories may
   still reuse voices. Explicit document voice defaults remain stronger than
   suggestions. Current manual corrections survive replanning, with conflicting
   AI suggestions flagged for review.
6. **Original** and **Directed** audition the same adjacent exchange, including
   a local and phone participant where available. Both use the reviewed cast and
   speed. Original uses source pauses and no acoustic effects; Directed uses the
   resolved natural gaps and effects used by export. The excerpt is two complete
   turns, not an arbitrary audio cut; very long turns or scripted pauses can make
   it longer. **Stop playback** stops Windows playback.
7. Choose **continue** or **stop** on failure and **Generate**. Current turn,
   per-file state and overall progress appear while workers run. Cancel stops
   new work, cancels the active operation cooperatively and cleans temporary
   chunks. Completed outputs survive. Select failed/cancelled files and **Retry
   selected failed files** to reuse the same validated settings. A changed plan
   starts a new run rather than retrying an older snapshot.
8. **Open output folder** and **View report** expose results. Each run writes a
   uniquely named `audio-director-report-*.json`; it contains file IDs, paths,
   hashes, applied controls and actionable diagnostics, without dialogue, raw
   prompts, raw model responses or credentials. Audio is validated and published
   atomically. Source JSON remains intact.

**Automatically generate** is opt-in. It runs after Build plan only if every
unskipped file passes validation, including assets and output conflicts. AI
ambiguities, unsupported requests and proposed provider substitutions block it.
Review the controls, resolve the choice, then explicitly accept current controls
in Review. That acceptance does not bypass missing models or invalid settings.

## Local LLM setup and connection test

The adapter supports a JSON-mode **OpenAI-compatible chat-completions endpoint**:
`POST <endpoint>/chat/completions`, `stream:false`, `response_format:{"type":
"json_object"}`, and `choices[0].message.content` containing a JSON plan. No tools
or shell actions are sent or accepted. This is compatible with the local API
documented in [Ollama's official compatibility guide](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx).
Use a locally installed instruction model that can follow the version-one
contract; availability and model names depend on your server configuration.

For an existing Ollama installation, run its server, install/load a local
instruction model of your choice, and obtain its exact name from `ollama list`.
The default endpoint is `http://127.0.0.1:11434/v1`. Other compatible local servers
can use a different loopback port and model name. The app does not install an LLM
or download weights. Enter the endpoint and exact model, then **Test connection**.
This performs a real inference request for `{"connected":true}` with no dialogue.
The equivalent repeatable command is:

```powershell
python -m scripts.check_director_llm --endpoint http://127.0.0.1:11434/v1 --model YOUR_INSTALLED_MODEL
```

`TTS_DIRECTOR_LLM_MODEL` supplies the initial UI model name. If required by the
endpoint, `TTS_DIRECTOR_LLM_API_KEY` supplies a Bearer token from the environment;
it is never saved in a preset/report. Requests time out after 90 seconds and can
be cancelled. Unreachable endpoints, non-200 responses, malformed envelopes,
non-JSON/duplicate keys, unknown fields and invalid plans receive setup/review
errors. Manual rendering remains available.

Only `localhost` and numeric loopback addresses are labelled local. Proxies are
ignored and HTTP redirects are rejected. Any other endpoint is labelled cloud,
requires HTTPS, requires disabling Fully offline, and requires explicitly enabling
**Allow sending batch metadata/content to this cloud LLM**. This covers filenames,
roles and direction text as well as dialogue. Fully offline requires a server
actually running a local model; a local proxy relaying to a cloud model cannot
provide offline operation. Use local weights and no proxy/remote backend.

Metadata is sent first: bounded relative file IDs, speaker IDs/roles, turn indexes,
explicit-pause flags, relevant voices (up to 96 per provider), verified model
availability, supported controls, formats and current settings. Input extensions
and delivery notes cannot issue actions. **Include short dialogue excerpts** is
an explicit opt-in when scene interpretation needs content (first eight turns,
up to 240 characters each). If metadata/excerpts cannot identify a scene, specify
the exact file, speaker IDs and segment range manually rather than accepting a
guess. Inventory is limited to 192 KiB and responses to 256 KiB.

## Worked Lessons example

Use `examples/audio_director/Lessons` as the input folder and a fresh output folder.
It contains clean narration, a two-speaker discussion, a host/remote-guest interview
and an invalid speaker reference. It includes omitted, explicit-zero, positive
and final pauses. To check conflicts, place an existing `01_narration.mp3` in the
output folder; review and rename it to `01_narration-reviewed.mp3` or explicitly
choose replacement.

With installed Kokoro assets, choose Kokoro and paste:

> Read the conversations in my Lessons folder. Use installed British Kokoro
> voices and keep recurring characters consistent across lessons. Make the
> exchanges feel like natural discussions. In the telephone interview, keep the
> host clear and make only the guest sound like they are on the phone. Preserve
> the scripted pauses, including the silence at the end. Export one MP3 per
> conversation. Continue with the other lessons if one file fails.

With AI enabled and a configured server, Build plan returns a locally validated,
editable proposal. Review recurring identities rather than inferring a cast from
display names. The fixture's explicit voices select `bm_george` and `bf_emma`.
Explicitly link `alex` across discussion and interview. For manual setup, choose
natural timing, then select the interview and set phone speaker `guest`, range
2–4. Room sound Off and no cues keep the example clear. The host's turns 1, 3
and 5 remain untreated. Choose continue; the three valid files can complete while
`04_malformed.json` reports its undeclared speaker. Select that file to inspect
the validation error; editing its source requires rescanning/review.

The repeatable real-local acceptance helper uses these public fixtures, installed
models only, a fresh output folder and explicit cast/phone settings. It does not
pretend to demonstrate the AI instruction when no LLM is configured:

```powershell
python -m scripts.director_acceptance --model-directory "C:\path\to\models" --output ".venv\director-acceptance-new"
```

It verifies a retained output conflict, three valid MP3 exports, one invalid
conversation, a two-turn phone audition and final scripted silence, with Python
DNS/connection helpers denied during synthesis. Review the listening sample and
full phone export separately from automated media validation.

## Timing, acoustics and limits

Turn-taking and acoustic settings are independent. **Clean narration** starts
with script timing, room Off and no cues. **Natural discussion** selects bounded
natural timing; acoustics remain optional. **Telephone interview** selects natural
timing and asks you to identify the remote participant; it never guesses a caller
or filters both sides automatically. Underlying controls remain editable.

The original version-one source snapshot distinguishes an omitted pause from an
explicit zero. Only omitted, nonfinal boundaries between different speakers can
receive automatic gaps. Short following replies use the minimum; longer replies
to a question use the maximum; other handoffs use the midpoint. Bounds are 0–2
seconds, default 0.12–0.45. Explicit zero, positive, intra-speaker and final pauses
remain intact. Legacy renderers still interpret omission as zero. Director timing
is an opt-in plan setting and never edits the source contract. The deterministic
resolved document is shared by audition/export/retry.

Phone treatment is a speech-only 300–3400 Hz band filter applied to the selected
speaker in the inclusive one-based segment range before combining. Both sides
can be selected explicitly. The treatment ends with that scope. Preserve complex
AI-generated disjoint scopes by leaving the phone form unchanged when applying
other selected-file edits; all scopes appear in Review.

Room **Off**, **Subtle** (0.002 amplitude) and **Custom** (0–0.015) use deterministic
locally generated brown noise during speech. Incidental paper/chair noises use
sparse, quiet, locally generated filtered noise. No third-party recordings,
downloads or licensed sound assets are used; these cues introduce no third-party
audio attribution or redistribution requirements. Cue frequency zero
means off; otherwise every N turns, minimum N=3. You can delete individual cue
lines. These are synthetic approximations, not realistic sound recordings.
All scripted silence stays pure silence, including the ending. A limiter prevents
new clipping; intelligibility and naturalness still require listening review.

No words are added, removed or rewritten. Only dialogue is synthesized. Role and
segment speed overrides retain their established precedence over job speed.
Providers without speed support reject explicit speed settings. Emotional style,
filler words, laughter, ringing, static, connection sounds and genuine overlapping
voices are unsupported in this release. Unsupported requests stay visible as
review issues. Accepting sequential timing never shortens scripted pauses or
discards a line. A tested multi-track mixer and external-agent transport are
follow-up work; the current planning/runner services are already Tk-independent.

Saved named Director presets retain scoped file/speaker settings without dialogue
or credentials. Apply them explicitly to a batch with the same file and speaker
IDs; unknown references are rejected and current manual corrections remain
stronger. Existing project/preset behavior in the JSON editor is unchanged;
Director starts from source documents, not implicitly from an unopened project.

Actual verification and remaining prerequisites are recorded in
[M18–M21 evidence](../milestones/M18_M21_AUDIO_DIRECTOR.md). In particular, a real
configured LLM and human listening review are distinct from fake-adapter and
synthetic-audio checks, and Windows 150%/200% scaling is not inferred from Tk font
scaling or 100% tests.
