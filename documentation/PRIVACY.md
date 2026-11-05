# DialogueFoundry privacy and local data

Piper and Kokoro synthesis run locally after runtimes and verified assets are
installed. Downloading packages or models contacts their hosting services.
Selecting Microsoft Edge TTS sends the text being synthesized and voice/request
information to Microsoft's online service. Local model selection does not make
an Edge or cloud-planning workflow offline.

## Optional planning

Audio Director manual planning and its direction-file CLI need no LLM request.
The optional planner sends an inventory including file/role identifiers, speaker
metadata, notes, selected direction and supported controls to the configured
endpoint. Dialogue excerpts or full conversation text can be included when you
opt in. Inspect your scripts' metadata as well as dialogue before sharing.

Only loopback endpoints are classified local. A local server is a separate
application: its retention, logging and any onward traffic are outside
DialogueFoundry's control. Nonlocal planning requires HTTPS, cloud consent and
offline mode disabled. OpenAI planning uses `OPENAI_API_KEY`; other endpoints can
use `TTS_DIRECTOR_LLM_API_KEY`. Do not put keys in source, direction files,
screenshots or bug reports. Check the endpoint provider's current terms and
retention settings. The app's consent checks are not a guarantee about that service.

## Stored files

- Source scripts, JSON exports and saved projects contain dialogue. Projects also
  retain settings and source provenance. Final audio reveals spoken content.
- Models persist in `%LOCALAPPDATA%\Windows TTS App\models`. Preview audio persists
  in the sibling `previews` cache and can reveal auditioned text.
- Ordinary generation can retain `audio_parts`, per-job chunks, silence files
  and `generation.json` beside output locations. Metadata uses hashes rather than
  dialogue bodies, but audio intermediates remain sensitive. Jobs do not resume
  automatically from these records.
- Director cleans its per-file temporary job directories during normal lifecycle
  cleanup. Reports and reviewed plans persist and include filenames, paths,
  provider/voice choices and diagnostic information. Abrupt process termination
  can leave temporary files behind.
- Errors/logging aim to avoid script bodies, credentials and raw planner replies;
  OS errors, filenames and third-party diagnostics can still reveal private data.

Close the app and wait for cancellation/worker cleanup before removing files.
Use Model library Remove for models. Delete unwanted previews, intermediates,
plans, reports, projects and outputs from the locations you selected; check backups
and synced folders too. Deletion is not secure erasure. Do not assume cancellation
deletes all previously completed audio. Share a fictional minimal reproduction and
redacted diagnostics following [Support](../SUPPORT.md).
