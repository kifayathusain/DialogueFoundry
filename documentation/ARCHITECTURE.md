# DialogueFoundry architecture

DialogueFoundry retains a Python `ttsapp` package and Tkinter desktop.
`app.py` launches the desktop or explicit diagnostics; `main.py` preserves legacy
no-argument text generation and dispatches explicit arguments to `cli.py` and
`director_cli.py`.

```text
Desktop / CLI -> validated document + voice mapping -> service
                                                     |
                              text processing -> generation
                                                     |
                               provider -> native MP3 / WAV
                                                     |
                             PCM processing -> validated export
```

`conversation_document.py` owns bounded immutable structured documents and atomic
source saves. `parser.py` handles legacy text. `speaker_mapping.py` resolves
assignments and effective settings; `project_storage.py` owns data-only projects
and presets. UI filtering never establishes speaker identity.

`service.py` is the widget-independent generation boundary. `generation.py`
coordinates ordered chunks, exact structured silence, progress, cancellation and
metadata. `text_processing.py` segments long input without placing FFmpeg logic
inside providers. Providers implement `providers/base.py`; Edge wraps the online
adapter, while Piper and Kokoro defer optional native imports until selected.

`ProviderManager` owns session lifetimes and verified model descriptors.
`models/catalog.py` and the pinned English JSON define known assets, source URLs,
sizes and hashes. `models/manager.py` installs/verifies/removes them without UI
dependencies. The library and preview interfaces communicate through worker events.

`audio_process.py` owns cancellable subprocess lifetimes and FFprobe calls.
`audio_export.py` handles layouts/codecs, normalization, validation and atomic final
publication. `audio_effects.py` handles scoped PCM treatments. Providers do not own
scene effects or media exports. `preview.py` owns the bounded audio cache and
Windows playback.

Director separates snapshots/plans (`director.py`), optional endpoint planning
(`director_planner.py`), catalog casting (`director_cast*.py`), rendering
(`director_runner.py`) and Tk controls (`director_gui.py`). The direction-file CLI
validates exact mixed-provider assignments and retains sessions until cleanup.
Planner proposals are validated data, not filesystem operations or executable tools.

Tk callbacks capture settings, start background work and process typed queued
events on the main thread. Preserve these boundaries when contributing. Keep
business rules testable without constructing widgets or calling real services.
See [Contributing](../CONTRIBUTING.md) for checks and
[Known limitations](KNOWN_LIMITATIONS.md) for validation gaps.
