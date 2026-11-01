"""Audio Director desktop workspace; workers own all I/O, planning and rendering."""

from __future__ import annotations

import asyncio
import json
import os
import queue
import tempfile
import threading
import tkinter as tk
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, replace
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any
from uuid import uuid4

from .director import (
    BatchPlan,
    FilePlan,
    IncidentalCue,
    PhoneScope,
    SceneSettings,
    TimingSettings,
    bind_cast,
    edit_file,
    manual_plan,
    plan_settings,
    preflight,
    resolved_document,
    scan_folder,
)
from .director_planner import LLMConnection, LocalLLMPlanner, apply_proposal
from .director_runner import (
    BatchEvent,
    FileResult,
    render_file,
    run_batch,
    save_report,
    verify_assets,
)
from .model_library import ModelLibraryWindow
from .models.manager import InstallationState
from .preview import WindowsAudioPlayer
from .project_storage import read_json_file, write_json_atomic
from .provider_manager import ProviderManager
from .providers.base import CancellationToken
from .speaker_mapping import resolve_document


@dataclass(frozen=True)
class DirectorEvent:
    """Revision-tagged worker message; widgets are touched only by the UI poller."""

    revision: int
    kind: str
    payload: object = None


class AudioDirectorWindow(tk.Toplevel):
    """Complete folder-to-files job using the shared, widget-free services."""

    def __init__(
        self, parent: tk.Misc, providers: ProviderManager | None = None
    ) -> None:
        super().__init__(parent)
        self.title("Audio Director")
        self.geometry("1024x768")
        self.minsize(480, 360)
        self.transient(parent)
        self.grab_set()
        self.providers = providers if providers is not None else ProviderManager()
        self.choices = self.providers.list_choices()
        self.plan: BatchPlan | None = None
        self.results: tuple[FileResult, ...] = ()
        self.errors: dict[str, tuple[str, ...]] = {}
        self._verified_settings: dict[str, str] = {}
        self.excluded: tuple[str, ...] = ()
        self._revision = 0
        self._worker: threading.Thread | None = None
        self._operation = ""
        self._closing = False
        self._library: ModelLibraryWindow | None = None
        self._token = CancellationToken()
        self._events: queue.Queue[DirectorEvent] = queue.Queue()
        self._cache = tempfile.TemporaryDirectory(prefix="tts-director-audition-")
        self._player = WindowsAudioPlayer()
        self._report: Path | None = None
        self._preview: Path | None = None
        self.source = tk.StringVar(
            master=self,
        )
        self.destination = tk.StringVar(
            master=self, value=str(Path.home() / "Documents" / "TTS Audio Director")
        )
        self.recursive = tk.BooleanVar(
            master=self,
        )
        self.audio_format = tk.StringVar(master=self, value="mp3")
        self.provider = tk.StringVar(
            master=self,
            value=next(
                (choice.provider_id for choice in self.choices if not choice.online),
                self.choices[0].provider_id,
            ),
        )
        self.offline = tk.BooleanVar(master=self, value=True)
        self.use_ai = tk.BooleanVar(
            master=self,
        )
        self.endpoint = tk.StringVar(master=self, value="http://127.0.0.1:11434/v1")
        self.model = tk.StringVar(
            master=self, value=os.environ.get("TTS_DIRECTOR_LLM_MODEL", "")
        )
        self.cloud = tk.BooleanVar(
            master=self,
        )
        self.excerpts = tk.BooleanVar(
            master=self,
        )
        self.automatic = tk.BooleanVar(
            master=self,
        )
        self.failure_policy = tk.StringVar(master=self, value="continue")
        self.status = tk.StringVar(
            master=self,
            value="Choose folders, describe or use manual setup, review, then Generate.",
        )
        self.summary = tk.StringVar(master=self, value="No folder scanned.")
        self._build()
        for editor in (self.direction, self.cues, self.details):
            editor.bind("<Tab>", self._traverse_text)
            editor.bind("<Shift-Tab>", self._traverse_text)
        for variable in (
            self.source,
            self.destination,
            self.recursive,
            self.audio_format,
        ):
            variable.trace_add("write", self._source_changed)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_id = self.after(80, self._poll)
        self.after_idle(self._focus_source)

    def _build(self) -> None:
        scroll = ttk.Frame(self)
        scroll.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(scroll, highlightthickness=0)
        vertical = ttk.Scrollbar(scroll, command=self.canvas.yview, takefocus=True)
        horizontal = ttk.Scrollbar(
            self, orient="horizontal", command=self.canvas.xview, takefocus=True
        )
        self.canvas.configure(
            yscrollcommand=vertical.set, xscrollcommand=horizontal.set
        )
        vertical.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        horizontal.pack(fill="x")
        self.body = ttk.Frame(self.canvas, padding=10)
        window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind(
            "<Configure>",
            lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(
                window, width=max(880, event.width)
            ),
        )
        self.bind("<FocusIn>", self._reveal_focus)
        self._build_sources()
        self._build_direction()
        self._build_files()
        self._build_job_controls()

    def _build_sources(self) -> None:
        """Build one focused area of the Director workspace."""
        source = ttk.LabelFrame(self.body, text="1. Source and destination", padding=8)
        source.pack(fill="x")
        self._folder(source, "Conversations", self.source)
        self._folder(source, "Output", self.destination)
        row = ttk.Frame(source)
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Include subfolders", variable=self.recursive).pack(
            side="left"
        )
        self._combo(
            row, "Format", self.audio_format, ("mp3", "wav", "m4a"), side="left"
        )
        ttk.Button(row, text="Scan folder", command=self.scan).pack(side="left", padx=8)
        ttk.Label(source, textvariable=self.summary).pack(anchor="w")

    def _build_direction(self) -> None:
        """Build one focused area of the Director workspace."""
        direction = ttk.LabelFrame(
            self.body, text="2. Direction and settings", padding=8
        )
        direction.pack(fill="x", pady=6)
        self.direction = tk.Text(direction, height=3, wrap="word")
        self.direction.pack(fill="x")
        row = ttk.Frame(direction)
        row.pack(fill="x")
        self._combo(
            row,
            "Manual/default provider",
            self.provider,
            tuple(choice.provider_id for choice in self.choices),
            side="left",
        )
        ttk.Checkbutton(row, text="Fully offline", variable=self.offline).pack(
            side="left"
        )
        ttk.Checkbutton(row, text="Use AI planner", variable=self.use_ai).pack(
            side="left"
        )
        self._entry(
            direction,
            "LLM endpoint (loopback = local; other hosts = cloud)",
            self.endpoint,
        )
        self._entry(direction, "LLM model", self.model)
        row = ttk.Frame(direction)
        row.pack(fill="x")
        ttk.Checkbutton(
            row,
            text="Allow sending batch metadata/content to this cloud LLM",
            variable=self.cloud,
        ).pack(side="left")
        ttk.Checkbutton(
            row,
            text="Include short dialogue excerpts for scene interpretation",
            variable=self.excerpts,
        ).pack(side="left")
        row = ttk.Frame(direction)
        row.pack(fill="x")
        ttk.Button(row, text="Test connection", command=self.test_connection).pack(
            side="left"
        )
        ttk.Button(row, text="Build plan", command=self.build_plan).pack(
            side="left", padx=4
        )
        ttk.Button(row, text="Model library", command=self._models).pack(side="left")
        ttk.Button(row, text="Save named preset", command=self.save_preset).pack(
            side="left", padx=4
        )
        ttk.Button(row, text="Apply preset", command=self.load_preset).pack(side="left")
        ttk.Checkbutton(
            direction,
            text="Automatically generate after Build plan only when every file is ready",
            variable=self.automatic,
        ).pack(anchor="w")

    def _build_files(self) -> None:
        """Build one focused area of the Director workspace."""
        files = ttk.LabelFrame(
            self.body,
            text="3. Files and plan (Ctrl/Shift selects files for explicit cast linking)",
            padding=8,
        )
        files.pack(fill="both", expand=True)
        self.files = ttk.Treeview(
            files,
            columns=("state", "provider", "scene", "destination"),
            height=5,
            selectmode="extended",
        )
        self.files.heading("#0", text="Input file")
        for name in ("state", "provider", "scene", "destination"):
            self.files.heading(name, text=name.title())
            self.files.column(name, width=125, stretch=True)
        self.files.column("#0", width=170)
        bar = ttk.Scrollbar(files, command=self.files.yview)
        self.files.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.files.pack(fill="x")
        self.files.bind("<<TreeviewSelect>>", self._select_file)
        self.tabs = ttk.Notebook(files)
        self.tabs.pack(fill="both", expand=True, pady=4)
        self.tabs.enable_traversal()
        self._build_file_settings()
        self._build_cast()
        self._build_review()

    def _build_file_settings(self) -> None:
        """Build one focused area of the Director workspace."""
        self.file_provider = tk.StringVar(
            master=self,
        )
        self.name = tk.StringVar(
            master=self,
        )
        self.speed = tk.StringVar(
            master=self,
        )
        self.skipped = tk.BooleanVar(
            master=self,
        )
        self.overwrite = tk.BooleanVar(
            master=self,
        )
        self.scope = tk.StringVar(master=self, value="selected file")
        self.timing = tk.StringVar(master=self, value="script")
        self.gap_min = tk.StringVar(master=self, value="0.12")
        self.gap_max = tk.StringVar(master=self, value="0.45")
        self.scene_preset = tk.StringVar(master=self, value="Clean narration")
        self.phone_speakers = tk.StringVar(
            master=self,
        )
        self.phone_start = tk.StringVar(master=self, value="1")
        self.phone_end = tk.StringVar(
            master=self,
        )
        self.room_mode = tk.StringVar(master=self, value="Off")
        self.room_level = tk.StringVar(master=self, value="0.002")
        self.cue_frequency = tk.StringVar(master=self, value="0")
        settings = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(settings, text="File, timing and scene")
        self._combo(
            settings,
            "Provider (one per conversation)",
            self.file_provider,
            tuple(choice.provider_id for choice in self.choices),
        )
        self._entry(settings, "Destination filename", self.name)
        self._entry(
            settings,
            "Job speed (blank = default; role/segment overrides remain stronger)",
            self.speed,
        )
        self._combo(settings, "Turn-taking", self.timing, ("script", "natural"))
        row = ttk.Frame(settings)
        row.pack(fill="x")
        self._entry(row, "Minimum eligible gap", self.gap_min, side="left")
        self._entry(row, "Maximum eligible gap", self.gap_max, side="left")
        self._combo(
            settings,
            "Scene preset",
            self.scene_preset,
            ("Clean narration", "Natural discussion", "Telephone interview"),
        )
        ttk.Button(
            settings, text="Use scene preset", command=self._scene_defaults
        ).pack(anchor="w")
        self._entry(
            settings,
            "Phone speaker IDs (comma-separated; blank = no phone treatment)",
            self.phone_speakers,
        )
        row = ttk.Frame(settings)
        row.pack(fill="x")
        self._entry(row, "Phone start segment", self.phone_start, side="left")
        self._entry(row, "Phone end segment", self.phone_end, side="left")
        self._combo(settings, "Room sound", self.room_mode, ("Off", "Subtle", "Custom"))
        self._entry(settings, "Custom room level (0–0.015)", self.room_level)
        self._entry(
            settings,
            "Cue frequency (0 = off, otherwise every N turns, N >= 3)",
            self.cue_frequency,
        )
        ttk.Label(
            settings,
            text="Cue list: one segment:paper or segment:chair per line; delete any cue to remove it.",
        ).pack(anchor="w")
        self.cues = tk.Text(settings, height=2, wrap="word")
        self.cues.pack(fill="x")
        row = ttk.Frame(settings)
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Skip", variable=self.skipped).pack(side="left")
        ttk.Checkbutton(
            row,
            text="Explicitly replace this existing destination",
            variable=self.overwrite,
        ).pack(side="left")
        self._combo(
            row,
            "Apply settings to",
            self.scope,
            ("selected file", "whole batch"),
            side="left",
        )
        ttk.Button(settings, text="Apply settings", command=self.apply_settings).pack(
            anchor="w", pady=4
        )

    def _build_cast(self) -> None:
        """Build one focused area of the Director workspace."""
        cast_page = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(cast_page, text="Cast")
        self.cast = ttk.Treeview(
            cast_page, columns=("voice", "locale", "availability"), height=5
        )
        self.cast.heading("#0", text="Speaker ID / role")
        for name in ("voice", "locale", "availability"):
            self.cast.heading(name, text=name.title())
            self.cast.column(name, width=150)
        self.cast.pack(fill="x")
        self.cast.bind("<<TreeviewSelect>>", self._select_cast)
        self.voice = tk.StringVar(
            master=self,
        )
        self.voice_box = ttk.Combobox(cast_page, textvariable=self.voice)
        self.voice_box.pack(fill="x")
        ttk.Button(
            cast_page, text="Apply voice to selected file", command=self.apply_voice
        ).pack(anchor="w")
        self.cast_name = tk.StringVar(master=self, value="Recurring cast")
        self._entry(cast_page, "Named cast (saved with preset)", self.cast_name)
        ttk.Button(
            cast_page,
            text="Link this speaker ID across selected files",
            command=self.link_voice,
        ).pack(anchor="w")

    def _build_review(self) -> None:
        """Build one focused area of the Director workspace."""
        review = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(review, text="Review and diagnostics")
        self.details = tk.Text(review, height=9, wrap="word", state="disabled")
        detail_bar = ttk.Scrollbar(review, command=self.details.yview)
        self.details.configure(yscrollcommand=detail_bar.set)
        detail_bar.pack(side="right", fill="y")
        self.details.pack(fill="both", expand=True)
        ttk.Button(
            review,
            text="Accept current controls / sequential handoff and clear AI review issues",
            command=self.accept_review,
        ).pack(anchor="w")

    def _build_job_controls(self) -> None:
        """Build one focused area of the Director workspace."""
        # Audition and job controls stay reachable while the detail area scrolls.
        audition = ttk.Frame(self, padding=(10, 4))
        audition.pack(fill="x")
        ttk.Label(audition, text="4. Audition same exchange:").pack(side="left")
        for mode in ("Original", "Directed"):
            ttk.Button(
                audition,
                text=mode,
                command=lambda selected=mode: self.preview(selected.lower()),
            ).pack(side="left", padx=4)
        ttk.Button(audition, text="Stop playback", command=self._player.stop).pack(
            side="left"
        )
        monitor = ttk.Frame(self, padding=(10, 4))
        monitor.pack(fill="x")
        self._combo(
            monitor,
            "On failure",
            self.failure_policy,
            ("continue", "stop"),
            side="left",
        )
        ttk.Button(monitor, text="5. Generate", command=self.generate).pack(
            side="left", padx=4
        )
        ttk.Button(
            monitor,
            text="Retry selected failed files",
            command=lambda: self.generate(retry=True),
        ).pack(side="left")
        ttk.Button(monitor, text="Cancel", command=self.cancel).pack(
            side="left", padx=4
        )
        row = ttk.Frame(self, padding=(10, 0))
        row.pack(fill="x")
        ttk.Button(row, text="Open output folder", command=self.open_output).pack(
            side="left"
        )
        ttk.Button(row, text="View report", command=self.view_report).pack(
            side="left", padx=4
        )
        self.progress = ttk.Progressbar(row, maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(self, textvariable=self.status, wraplength=950, padding=(10, 4)).pack(
            fill="x"
        )

    def _folder(self, parent: tk.Misc, label: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Label(row, text=label, width=15).pack(side="left")
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side="left", fill="x", expand=True)
        if variable is self.source:
            self._source_entry = entry
        ttk.Button(row, text="Browse…", command=lambda: self._browse(variable)).pack(
            side="left", padx=4
        )

    def _browse(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(parent=self)
        if selected:
            variable.set(selected)

    def _focus_source(self) -> None:
        self._source_entry.focus_set()
        self.canvas.yview_moveto(0)

    @staticmethod
    def _traverse_text(event: tk.Event) -> str:
        if event.state & 1:
            target = event.widget.tk_focusPrev()
        else:
            target = event.widget.tk_focusNext()
        if target is not None:
            target.focus_set()
        return "break"

    @staticmethod
    def _entry(
        parent: tk.Misc, label: str, variable: tk.StringVar, *, side: str = "top"
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", side=side)
        ttk.Label(row, text=label).pack(side="left")
        ttk.Entry(row, textvariable=variable, width=18).pack(
            side="left", fill="x", expand=True, padx=4
        )

    @staticmethod
    def _combo(
        parent: tk.Misc,
        label: str,
        variable: tk.StringVar,
        values: tuple,
        *,
        side: str = "top",
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", side=side)
        ttk.Label(row, text=label).pack(side="left")
        ttk.Combobox(
            row, textvariable=variable, values=values, state="readonly", width=20
        ).pack(side="left", padx=4)

    def _source_changed(self, *args: object) -> None:
        self._revision += 1
        self._token.cancel()
        self._player.stop()
        self.plan = None
        self.results = ()
        self.errors = {}
        self._verified_settings.clear()
        self.files.delete(*self.files.get_children())
        self.summary.set("Source, destination or format changed; scan again.")

    def _reveal_focus(self, event: tk.Event) -> None:
        widget = event.widget
        if str(widget).startswith(str(self.body)):
            self.update_idletasks()
            height = max(1, self.body.winfo_height())
            top = widget.winfo_rooty() - self.body.winfo_rooty()
            visible_top = self.canvas.canvasy(0)
            if (
                top < visible_top
                or top + widget.winfo_height()
                > visible_top + self.canvas.winfo_height()
            ):
                self.canvas.yview_moveto(max(0, top - 16) / height)

    def _start(
        self, kind: str, operation: Callable[[], Coroutine[Any, Any, object]]
    ) -> None:
        if self._worker is not None:
            return
        self._revision += 1
        revision = self._revision
        self._token = CancellationToken()
        self._operation = kind
        self._set_busy(True)
        self._player.stop()
        self.status.set(f"{kind}… Cancel remains available.")

        def worker() -> None:
            try:
                payload = asyncio.run(operation())
                self._events.put(DirectorEvent(revision, kind, payload))
            except asyncio.CancelledError:
                self._events.put(DirectorEvent(revision, "cancelled"))
            except Exception as error:
                self._events.put(DirectorEvent(revision, "error", str(error)))
            finally:
                self._events.put(DirectorEvent(revision, "idle"))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        """Freeze captured inputs while a worker owns their immutable snapshot."""
        if busy:
            self._widget_states = []
            pending = list(self.winfo_children())
            while pending:
                widget = pending.pop()
                pending.extend(widget.winfo_children())
                if isinstance(
                    widget,
                    (ttk.Entry, ttk.Combobox, ttk.Button, ttk.Checkbutton, tk.Text),
                ):
                    if isinstance(widget, ttk.Button) and widget.cget("text") in {
                        "Cancel",
                        "Stop playback",
                    }:
                        continue
                    state = str(widget.cget("state"))
                    self._widget_states.append((widget, state))
                    widget.configure(state="disabled")
        else:
            for widget, state in getattr(self, "_widget_states", ()):
                if widget.winfo_exists():
                    widget.configure(state=state)
            self._widget_states = []

    def scan(self) -> None:
        if self._worker is not None:
            return
        source, destination = Path(self.source.get()), Path(self.destination.get())
        recursive, audio_format, offline = (
            self.recursive.get(),
            self.audio_format.get(),
            self.offline.get(),
        )
        choice = next(
            choice
            for choice in self.choices
            if choice.provider_id == self.provider.get()
        )

        async def operation() -> object:
            scan = scan_folder(source, recursive, self._token)
            plan = manual_plan(
                scan,
                source,
                destination,
                choice,
                audio_format=audio_format,
                offline=offline,
            )
            return (
                plan,
                scan.excluded,
                preflight(plan, self.choices, check_sources=True),
            )

        self._start("Scan", operation)

    def _connection(self) -> LLMConnection:
        return LLMConnection(
            self.endpoint.get().strip(), self.model.get().strip(), self.cloud.get()
        )

    def test_connection(self) -> None:
        planner = LocalLLMPlanner(self._connection())
        offline = self.offline.get()

        async def operation() -> object:
            return await planner.test_connection(self._token, offline=offline)

        self._start("Connection", operation)

    def build_plan(self) -> None:
        if self.plan is None:
            self.status.set("Scan a folder first.")
            return
        if self._worker is not None:
            return
        plan = replace(
            self.plan,
            offline=self.offline.get(),
            failure_policy=self.failure_policy.get(),
        )
        direction = self.direction.get("1.0", "end").strip()
        use_ai, excerpts = self.use_ai.get(), self.excerpts.get()
        planner = LocalLLMPlanner(self._connection())
        default_choice = next(
            choice
            for choice in self.choices
            if choice.provider_id == self.provider.get()
        )

        async def operation() -> object:
            current = plan
            if use_ai:
                availability = {}
                for manifest in self.providers.models.list_models():
                    self._token.raise_if_cancelled()
                    availability[manifest.model_id] = (
                        self.providers.models.status(manifest.model_id)
                        == InstallationState.INSTALLED
                    )
                current = await planner.build(
                    direction,
                    current,
                    self.choices,
                    self._token,
                    include_excerpts=excerpts,
                    availability=availability,
                )
            else:
                files = []
                for item in current.files:
                    if (
                        item.source.document is not None
                        and "provider_id" not in item.manual_fields
                        and item.provider_id != default_choice.provider_id
                    ):
                        resolved = resolve_document(
                            item.source.document, default_choice, locale="en-GB"
                        )
                        item = replace(
                            item,
                            provider_id=default_choice.provider_id,
                            cast=tuple(
                                (assignment.speaker_id, assignment.voice_id)
                                for assignment in resolved.assignments
                            ),
                        )
                    files.append(item)
                current = replace(
                    current, files=tuple(files), revision=current.revision + 1
                )
            return (
                current,
                self.excluded,
                verify_assets(current, self.providers, self._token),
            )

        self._start("Plan", operation)

    def _selected(self) -> FilePlan:
        if self.plan is None or not self.files.selection():
            raise ValueError("Select a conversation file first.")
        return next(
            item
            for item in self.plan.files
            if item.source.file_id == self.files.selection()[0]
        )

    def _refresh(self) -> None:
        if self.plan is None:
            return
        selected = self.files.selection()
        self.files.delete(*self.files.get_children())
        states = {item.file_id: item.state for item in self.results}
        for item in self.plan.files:
            state = states.get(item.source.file_id)
            if state is None:
                if item.skipped:
                    state = "skipped"
                elif self.errors.get(item.source.file_id):
                    state = "blocked"
                elif self._verified_settings.get(
                    item.source.file_id
                ) == self._settings_identity(item):
                    state = "ready"
                else:
                    state = "ready (verify assets)"
            scene = "clean"
            if item.scene.phone:
                scene = "telephone"
            elif item.scene.room_level:
                scene = "room"
            self.files.insert(
                "",
                "end",
                iid=item.source.file_id,
                text=item.source.file_id,
                values=(state, item.provider_id, scene, item.destination_name),
            )
        ready = sum(
            not item.skipped
            and not self.errors.get(item.source.file_id)
            and states.get(item.source.file_id) != "completed"
            for item in self.plan.files
        )
        blocked = sum(
            not item.skipped
            and bool(self.errors.get(item.source.file_id))
            and states.get(item.source.file_id) != "completed"
            for item in self.plan.files
        )
        self.summary.set(
            f"{ready} ready · {blocked} need attention · {len(self.excluded)} excluded (see Review) · {sum(item.skipped for item in self.plan.files)} skipped · {sum(state == 'completed' for state in states.values())} completed"
        )
        retained = [file_id for file_id in selected if self.files.exists(file_id)]
        if retained or self.plan.files:
            self.files.selection_set(retained or (self.plan.files[0].source.file_id,))
            self._select_file()

    def _select_file(self, event: tk.Event | None = None) -> None:
        if (
            self._worker is not None
            and self._operation == "Preview"
            and self.files.selection() != getattr(self, "_preview_selection", ())
        ):
            self._token.cancel()
            self._revision += 1
        try:
            item = self._selected()
        except ValueError:
            return
        self.file_provider.set(item.provider_id)
        self.name.set(item.destination_name)
        self.speed.set("" if item.speed is None else str(item.speed))
        self.timing.set(item.timing.mode)
        self.gap_min.set(str(item.timing.minimum))
        self.gap_max.set(str(item.timing.maximum))
        self.skipped.set(item.skipped)
        self.overwrite.set(item.overwrite)
        self.room_mode.set("Off" if not item.scene.room_level else "Custom")
        self.room_level.set(str(item.scene.room_level))
        self.phone_speakers.set(
            ",".join(dict.fromkeys(scope.speaker for scope in item.scene.phone))
        )
        self.phone_start.set(str(item.scene.phone[0].start if item.scene.phone else 1))
        phone_end = 1
        if item.scene.phone:
            phone_end = item.scene.phone[0].end
        elif item.source.document:
            phone_end = len(item.source.document.segments)
        self.phone_end.set(str(phone_end))
        self._phone_snapshot = (
            self.phone_speakers.get(),
            self.phone_start.get(),
            self.phone_end.get(),
        )
        self.cues.configure(state="normal")
        self.cues.delete("1.0", "end")
        self.cues.insert(
            "1.0", "\n".join(f"{cue.segment}:{cue.kind}" for cue in item.scene.cues)
        )
        self.cue_frequency.set("0")
        choice = next(
            (
                choice
                for choice in self.choices
                if choice.provider_id == item.provider_id
            ),
            None,
        )
        voices = {voice.voice_id: voice for voice in choice.voices} if choice else {}
        self.voice_box.configure(values=tuple(voices))
        self.cast.delete(*self.cast.get_children())
        details = list(self.errors.get(item.source.file_id, ()))
        details.extend(item.issues)
        if item.source.document:
            for speaker in item.source.document.speakers:
                voice = dict(item.cast).get(speaker.id, "")
                metadata = voices.get(voice)
                availability = "Verify with Build plan"
                if self.errors.get(item.source.file_id):
                    availability = "Needs attention"
                elif self._verified_settings.get(
                    item.source.file_id
                ) == self._settings_identity(item):
                    availability = "Verified by Build plan"
                self.cast.insert(
                    "",
                    "end",
                    iid=speaker.id,
                    text=f"{speaker.id} / {speaker.role}",
                    values=(
                        voice,
                        metadata.language if metadata else "Unknown",
                        availability,
                    ),
                )
            resolved = resolved_document(item)
            for index, (source, segment) in enumerate(
                zip(
                    item.source.document.to_dict()["segments"],
                    resolved.segments,
                    strict=True,
                ),
                1,
            ):
                timing = (
                    "scripted"
                    if "pause_after_seconds" in source
                    else "eligible/omitted"
                )
                details.append(
                    f"Turn {index}: {segment.speaker}, after-pause {segment.pause_after_seconds}s ({timing})."
                )
        details.append("Actual controls: " + str(plan_settings(item)))
        details.append(
            "LLM: "
            + (
                "Local loopback"
                if self._connection().local
                else "Cloud; explicit consent required"
            )
            + "; TTS: "
            + ("Online" if choice and choice.online else "Local")
        )
        details.extend(f"Excluded: {entry}" for entry in self.excluded)
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(details))
        self.details.configure(state="disabled")

    @staticmethod
    def _settings_identity(item: FilePlan) -> str:
        return json.dumps(
            {"source": item.source.fingerprint, "settings": plan_settings(item)},
            sort_keys=True,
        )

    def _select_cast(self, event: tk.Event | None = None) -> None:
        if self.cast.selection():
            self.voice.set(self.cast.item(self.cast.selection()[0], "values")[0])

    def _edit(self, file_id: str, **changes: object) -> None:
        if self.plan is None or self._worker is not None:
            return
        self.plan = edit_file(self.plan, file_id, **changes)
        self._revision += 1
        self.results = ()
        self._player.stop()
        self._preview = None
        self.errors = preflight(self.plan, self.choices)
        self._refresh()

    def _scene_defaults(self) -> None:
        preset = self.scene_preset.get()
        self.timing.set("script" if preset == "Clean narration" else "natural")
        self.room_mode.set("Off")
        self.cues.delete("1.0", "end")
        if preset != "Telephone interview":
            self.phone_speakers.set("")
        else:
            self.status.set(
                "Choose the remote speaker ID and segment range; the host stays clear."
            )

    def apply_settings(self) -> None:
        if self._worker is not None:
            return
        try:
            item = self._selected()
            timing = TimingSettings(
                self.timing.get(), float(self.gap_min.get()), float(self.gap_max.get())
            )
            level = {"Off": 0, "Subtle": 0.002}.get(self.room_mode.get())
            if level is None:
                level = float(self.room_level.get())
            cues = []
            for line in self.cues.get("1.0", "end").strip().splitlines():
                index, kind = line.strip().split(":")
                cues.append(IncidentalCue(int(index), kind.strip()))
            frequency = int(self.cue_frequency.get())
            if frequency and frequency < 3:
                raise ValueError("Cue frequency must be zero or at least three turns.")
            speakers = tuple(
                speaker.strip()
                for speaker in self.phone_speakers.get().split(",")
                if speaker.strip()
            )
            start, end = int(self.phone_start.get()), int(self.phone_end.get())
            targets = self.plan.files if self.scope.get() == "whole batch" else (item,)
            plan = self.plan
            for target in targets:
                if target.source.document is None:
                    continue
                generated = cues
                if frequency:
                    generated = [
                        IncidentalCue(index, "paper")
                        for index in range(
                            frequency,
                            len(target.source.document.segments) + 1,
                            frequency,
                        )
                    ]
                phone = tuple(PhoneScope(speaker, start, end) for speaker in speakers)
                if (
                    self.scope.get() == "selected file"
                    and (
                        self.phone_speakers.get(),
                        self.phone_start.get(),
                        self.phone_end.get(),
                    )
                    == self._phone_snapshot
                ):
                    phone = target.scene.phone
                scene = SceneSettings(
                    phone,
                    level,
                    tuple(generated),
                )
                choice = next(
                    choice
                    for choice in self.choices
                    if choice.provider_id == self.file_provider.get()
                )
                cast = target.cast
                if target.provider_id != choice.provider_id:
                    resolved = resolve_document(
                        target.source.document, choice, locale="en-GB"
                    )
                    cast = tuple(
                        (voice.speaker_id, voice.voice_id)
                        for voice in resolved.assignments
                    )
                changes = {
                    "provider_id": choice.provider_id,
                    "speed": float(self.speed.get())
                    if self.speed.get().strip()
                    else None,
                    "timing": timing,
                    "scene": scene,
                }
                if target.provider_id != choice.provider_id:
                    changes["cast"] = cast
                if target.source.file_id == item.source.file_id:
                    changes.update(
                        destination_name=self.name.get().strip(),
                        overwrite=self.overwrite.get(),
                        skipped=self.skipped.get(),
                    )
                plan = edit_file(plan, target.source.file_id, **changes)
            self.plan = plan
            self._revision += 1
            self.results = ()
            self.errors = preflight(plan, self.choices)
            self._refresh()
        except (ValueError, StopIteration) as error:
            self.status.set(str(error) or "Select a known provider.")

    def apply_voice(self) -> None:
        try:
            item = self._selected()
            if not self.cast.selection():
                raise ValueError("Select a speaker in the Cast tab.")
            cast = dict(item.cast)
            cast[self.cast.selection()[0]] = self.voice.get().strip()
            self._edit(item.source.file_id, cast=tuple(cast.items()))
        except ValueError as error:
            self.status.set(str(error))

    def link_voice(self) -> None:
        if self._worker is not None:
            return
        try:
            if not self.cast.selection():
                raise ValueError(
                    "Select a source speaker, then select the files to link."
                )
            speaker = self.cast.selection()[0]
            members = tuple((file_id, speaker) for file_id in self.files.selection())
            self.plan = bind_cast(self.plan, members, self.voice.get().strip())
            self._revision += 1
            self.errors = preflight(self.plan, self.choices)
            self._refresh()
        except ValueError as error:
            self.status.set(str(error))

    def accept_review(self) -> None:
        try:
            item = self._selected()
            self._edit(item.source.file_id, issues=())
        except ValueError as error:
            self.status.set(str(error))

    def preview(self, mode: str) -> None:
        if self._worker is not None:
            return
        try:
            item = self._selected()
            plan = replace(
                self.plan,
                files=(replace(item, overwrite=True),),
                offline=self.offline.get(),
            )
        except ValueError as error:
            self.status.set(str(error))
            return
        output = Path(self._cache.name) / f"{mode}.wav"
        self._preview_selection = self.files.selection()

        async def operation() -> object:
            errors = verify_assets(plan, self.providers, self._token)[
                item.source.file_id
            ]
            if errors:
                raise ValueError("; ".join(errors))
            return await render_file(
                plan,
                item,
                self.providers,
                self._token,
                preview=mode,
                preview_output=output,
            )

        self._start("Preview", operation)

    def generate(self, retry: bool = False) -> None:
        if self.plan is None or self._worker is not None:
            return
        plan = replace(
            self.plan,
            offline=self.offline.get(),
            failure_policy=self.failure_policy.get(),
        )
        previous = self.results
        retry_ids = frozenset(self.files.selection()) if retry else None
        revision = self._revision + 1

        async def operation() -> object:
            self._token.raise_if_cancelled()
            results = await run_batch(
                plan,
                self.providers,
                self._token,
                previous=previous if retry else (),
                retry_ids=retry_ids,
                on_event=lambda event: self._events.put(
                    DirectorEvent(revision, "progress", event)
                ),
            )
            plan.output_folder.mkdir(parents=True, exist_ok=True)
            report = (
                plan.output_folder / f"audio-director-report-{uuid4().hex[:12]}.json"
            )
            save_report(plan, results, report)
            return plan, results, report

        self._start("Generate", operation)

    def save_preset(self) -> None:
        if self.plan is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".json",
            title="Save named Audio Director preset",
        )
        if not path:
            return
        plan, name = self.plan, self.cast_name.get()

        async def operation() -> object:
            return write_json_atomic(
                {
                    "kind": "audio_director_preset",
                    "schema_version": 1,
                    "name": name,
                    "failure_policy": plan.failure_policy,
                    "audio_format": plan.audio_format,
                    "files": [
                        {
                            "file_id": item.source.file_id,
                            **plan_settings(item),
                            "issues": [],
                        }
                        for item in plan.files
                        if item.source.document
                    ],
                },
                Path(path),
            )

        self._start("Saved preset", operation)

    def load_preset(self) -> None:
        if self.plan is None:
            return
        path = filedialog.askopenfilename(
            parent=self, filetypes=[("Director preset", "*.json")]
        )
        if not path:
            return
        plan = self.plan

        async def operation() -> object:
            data = read_json_file(Path(path), limit=256 * 1024)
            if (
                not isinstance(data, dict)
                or data.get("kind") != "audio_director_preset"
                or set(data)
                != {
                    "kind",
                    "schema_version",
                    "name",
                    "failure_policy",
                    "audio_format",
                    "files",
                }
            ):
                raise ValueError("Select an Audio Director preset.")
            proposal = {
                key: value for key, value in data.items() if key not in {"kind", "name"}
            }
            current = apply_proposal(plan, proposal, self.choices)
            return (
                current,
                self.excluded,
                verify_assets(current, self.providers, self._token),
            )

        self._start("Plan", operation)

    def _models(self) -> None:
        if self._worker is None:
            if self._library is not None and self._library.winfo_exists():
                self._library.lift()
            else:
                self._library = ModelLibraryWindow(
                    self, self.providers.models, self.providers.close
                )

    def cancel(self) -> None:
        self._token.cancel()
        self.status.set(
            "Cancelling; waiting for active operation cleanup. Completed files are retained."
        )

    def open_output(self) -> None:
        if self.plan is not None and self.plan.output_folder.is_dir():
            os.startfile(self.plan.output_folder)

    def view_report(self) -> None:
        if self._report is not None and self._report.is_file():
            os.startfile(self._report)

    def _poll(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if event.kind == "idle":
                continue
            if event.revision != self._revision or self._closing:
                continue
            if self._token.is_cancelled and event.kind in {
                "Scan",
                "Plan",
                "Preview",
                "Connection",
            }:
                continue
            if event.kind in {"Scan", "Plan"}:
                self.plan, self.excluded, self.errors = event.payload
                if event.kind == "Plan":
                    self._verified_settings = {
                        item.source.file_id: self._settings_identity(item)
                        for item in self.plan.files
                        if not self.errors.get(item.source.file_id) and not item.skipped
                    }
                self.results = ()
                self._refresh()
                self.status.set(
                    "Review controls and diagnostics, audition, or Generate."
                )
                if (
                    event.kind == "Plan"
                    and self.automatic.get()
                    and not any(self.errors.values())
                    and self.plan.files
                ):
                    self.after(120, self.generate)
            elif event.kind == "Preview":
                self._preview = event.payload
                self._player.play(self._preview)
                self.status.set("Playing the reviewed multi-turn exchange.")
            elif event.kind == "Generate":
                self.plan, self.results, self._report = event.payload
                self.errors = preflight(self.plan, self.choices)
                self._refresh()
                self.status.set(
                    f"Finished: {sum(item.state == 'completed' for item in self.results)} completed, {sum(item.state == 'failed' for item in self.results)} failed, {sum(item.state == 'cancelled' for item in self.results)} cancelled. Open output, view report or retry selected files."
                )
            elif event.kind == "progress":
                progress: BatchEvent = event.payload
                if self.files.exists(progress.file_id):
                    values = list(self.files.item(progress.file_id, "values"))
                    values[0] = progress.state
                    self.files.item(progress.file_id, values=values)
                fraction = progress.turn / progress.turns if progress.turns else 0
                self.progress["value"] = (
                    100
                    * min(progress.total, progress.completed + fraction)
                    / max(1, progress.total)
                )
                self.status.set(
                    f"{progress.file_id}: {progress.state}, turn {progress.turn}/{progress.turns}, overall {progress.completed}/{progress.total}"
                )
            else:
                self.status.set(
                    str(event.payload)
                    if event.payload
                    else "Cancelled; ready to retry."
                )
        if self._worker is not None and not self._worker.is_alive():
            self._worker = None
            self._set_busy(False)
        library_open = self._library is not None and self._library.winfo_exists()
        if self._closing and self._worker is None and not library_open:
            if self._operation != "Closing sessions":

                async def cleanup() -> object:
                    self.providers.close()
                    return None

                self._start("Closing sessions", cleanup)
                self._poll_id = self.after(80, self._poll)
                return
            self._cache.cleanup()
            self.destroy()
            return
        self._poll_id = self.after(80, self._poll)

    def close(self) -> None:
        """Wait asynchronously for cancellation and native-resource cleanup."""
        self._closing = True
        self._player.stop()
        self.cancel()
        if self._library is not None and self._library.winfo_exists():
            self._library._close()
