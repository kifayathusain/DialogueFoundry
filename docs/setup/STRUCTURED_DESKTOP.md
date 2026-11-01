# Structured desktop workflow

Launch the existing Tkinter app with `python app.py`. This is a single-provider
workflow; Edge requires internet for user-operated synthesis, and local providers
require already installed verified assets. Import, mapping and filtering never
download models or synthesize previews.

1. Use **Open / Import** for a .json or .txt file. Large input reading/validation
   runs in a worker; failure leaves the current JSON snapshot and mappings intact.
   The **Plain text** and **JSON** tabs retain separate sources; no lossy automatic
   conversion is offered.
2. In JSON's **Roles**, choose any declared role, enter a stable Edge ID or select
   a catalog local voice, inspect origin/locale/model guidance, and **Apply role**.
   IDs remain fixed when display labels change. Every declared role is listed,
   including unused ones. Provider switching restores assignments by stable ID.
   Search affects suggestions and keeps the selected ID.
3. In **Segments**, choose an ordered segment and edit dialogue, speaker,
   after-pause, optional speed and note, then **Apply segment**. Blank speed means
   inherit; explicit numeric speed must be 0.5–2.0 and supported by the provider.
   The speaker dropdown includes all declared roles. Source extensions survive.
4. Inspect counts and total/final explicit silence. **Validation** lists semantic
   paths; selecting a role/segment diagnostic navigates to it. Shared voices are
   warned about. Directions are visible notes; prose emotion/style is not applied.
5. **Preview speech only** uses the selected role's selected segment, or its first
   dialogue, and effective supported speed. After-pauses are omitted. Preview is
   explicit and revision-sensitive; changed settings invalidate stale results.
   An unused role with no dialogue reports that limitation.
6. Choose an output path. Expand **Advanced export options** for WAV/MP3/M4A,
   bitrate, sample rate, channels or normalization. JSON always uses processed
   generation and its explicit after-pauses; the legacy paragraph control is
   disabled in JSON. Sentence pauses are optional intra-segment additions.
7. **Generate** captures a consistent snapshot. Edits made during a job cannot
   change that job's requests. **Cancel** waits for provider/process cleanup and
   preserves previous final audio. **Play / Replay** and **Stop** retain preview
   playback controls. **Model library...** remains the user-operated installation
   and integrity-verification workflow.
8. **JSON Save As** writes only source JSON. **Save project As** includes active
   assignments/settings and clears project dirty state. Before replacing/closing
   unsaved JSON work, choose Save project, Discard or Cancel. Apply pending form
   edits before saving or generating. Imported sources are never implicit saves.

Role/segment lists use a fixed number of editor widgets rather than thousands of
complete rows. Scrollbars, nested tabs, native keyboard traversal and automatic
focus scrolling keep editing/action controls reachable at narrow sizes. Generate,
Cancel, Replay and Stop sit outside the scrolling editor. Long labels/IDs remain
stable identities; the selected role editor exposes full text.

## Layout and acceptance observations

The fake-provider Windows suite constructs real Tk windows, checks 1/3/20/1,000
roles, long labels and a 305-character ID, keyboard tree navigation, automatic
focus scrolling, 1024×768 and 512×384 windows, imports, edits, previews, cancellation
and graceful close. Actual host report: 1920×1080 screen, window DPI 96 (100%),
Tk scaling 1.3333333333333333, 1024×768 acceptance window.

Required actual Windows 150% and 200% OS scaling checks remain unverified.
Computer Use could list apps, but launching Windows Settings returned
"Computer Use app approval timed out". No display setting was changed. Tk scaling
emulation is not counted as OS scaling evidence. Exhaustive all-controls keyboard
review at those scaling modes is also outstanding. M15 stays BLOCKED; M16/M17
cannot pass their dependency gates until this evidence exists. No real-provider,
voice-quality, clean-machine or package acceptance is claimed by these UI tests.
