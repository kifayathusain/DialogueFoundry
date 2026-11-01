"""Tkinter structured document view; business rules remain in document/resolver."""

import re
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from .conversation_document import ConversationDocument, DocumentValidationError
from .provider_manager import ProviderChoice
from .speaker_mapping import MappingState, Preflight, ResolvedSegment, resolve_document


class StructuredEditor(ttk.Frame):
    """Bounded widget count for arbitrary role and segment lists."""

    def __init__(
        self,
        parent: tk.Misc,
        changed: Callable[[], None],
        preview: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.document: ConversationDocument | None = None
        self.mappings = MappingState()
        self.project_assignments: dict[str, dict[str, str]] = {}
        self.preferences: dict[tuple[str, str, str], str] = {}
        self.dirty = False
        self.pending_role = False
        self.pending_segment = False
        self._refreshing = False
        self._role_key: str | None = None
        self._segment_key: str | None = None
        self._changed = changed
        self._choice: ProviderChoice | None = None
        self._job_speed: float | None = None
        self._locale = "en-US"
        self._file_presence: dict[str, bool] = {}
        self._summary = tk.StringVar(value="Open a JSON conversation to begin.")
        ttk.Label(self, textvariable=self._summary, wraplength=650).pack(fill="x")
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        self.tabs.enable_traversal()
        self.roles, role_page = self._list_page("Roles")
        self.segments, segment_page = self._list_page("Segments")
        self.diagnostics, _ = self._list_page("Validation")
        self.role_name = tk.StringVar()
        self.role_voice = tk.StringVar()
        self.role_speed = tk.StringVar()
        self.role_note = tk.StringVar()
        self.role_info = tk.StringVar()
        self.segment_speaker = tk.StringVar()
        self.segment_pause = tk.StringVar()
        self.segment_speed = tk.StringVar()
        self.segment_note = tk.StringVar()
        self._entry(role_page, "Display role (ID stays fixed)", self.role_name)
        ttk.Label(role_page, text="Stable voice ID").pack(anchor="w")
        self.voice_box = ttk.Combobox(role_page, textvariable=self.role_voice)
        self.voice_box.pack(fill="x")
        self._entry(role_page, "Speed override (blank = inherit)", self.role_speed)
        self._entry(
            role_page, "Direction note (prose style is not applied)", self.role_note
        )
        ttk.Label(role_page, textvariable=self.role_info, wraplength=650).pack(fill="x")
        actions = ttk.Frame(role_page)
        actions.pack(fill="x", pady=4)
        ttk.Button(actions, text="Apply role", command=self.apply_role).pack(
            side="left"
        )
        ttk.Button(actions, text="Reset voice", command=self.reset_role).pack(
            side="left"
        )
        ttk.Button(actions, text="Preview speech only", command=preview).pack(
            side="left"
        )
        ttk.Label(segment_page, text="Speaker: Role (id)").pack(anchor="w")
        self.speaker_box = ttk.Combobox(
            segment_page,
            textvariable=self.segment_speaker,
            state="readonly",
        )
        self.speaker_box.pack(fill="x")
        self.dialogue = tk.Text(segment_page, height=4, wrap="word", undo=True)
        scrollbar = ttk.Scrollbar(segment_page, command=self.dialogue.yview)
        self.dialogue.configure(yscrollcommand=scrollbar.set)
        self.dialogue.pack(fill="both", expand=True)
        scrollbar.pack(fill="x")
        self._entry(
            segment_page,
            "After-pause seconds (including final segment)",
            self.segment_pause,
        )
        self._entry(
            segment_page, "Speed override (blank = inherit)", self.segment_speed
        )
        self._entry(segment_page, "Direction note (not spoken)", self.segment_note)
        ttk.Button(segment_page, text="Apply segment", command=self.apply_segment).pack(
            anchor="w", pady=4
        )
        self.roles.bind("<<TreeviewSelect>>", self._select_role)
        self.segments.bind("<<TreeviewSelect>>", self._select_segment)
        self.diagnostics.bind("<<TreeviewSelect>>", self._select_diagnostic)
        for variables, form in (
            (
                (self.role_name, self.role_voice, self.role_speed, self.role_note),
                "role",
            ),
            (
                (
                    self.segment_speaker,
                    self.segment_pause,
                    self.segment_speed,
                    self.segment_note,
                ),
                "segment",
            ),
        ):
            for variable in variables:
                variable.trace_add(
                    "write", lambda *args, kind=form: self._form_changed(kind)
                )
        self.dialogue.bind("<<Modified>>", self._dialogue_changed)
        self._diagnostic_paths: dict[str, str] = {}

    def _list_page(self, name: str) -> tuple[ttk.Treeview, ttk.Frame]:
        page = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(page, text=name)
        frame = ttk.Frame(page)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, show="tree", height=5, selectmode="browse")
        tree.column("#0", width=1000, minwidth=240)
        vertical = ttk.Scrollbar(frame, command=tree.yview)
        horizontal = ttk.Scrollbar(page, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.pack(side="left", fill="both", expand=True)
        vertical.pack(side="right", fill="y")
        horizontal.pack(fill="x")
        return tree, page

    @staticmethod
    def _entry(parent: tk.Misc, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).pack(anchor="w")
        ttk.Entry(parent, textvariable=variable).pack(fill="x")

    @property
    def pending(self) -> bool:
        """Whether either form has unapplied input."""
        return self.pending_role or self.pending_segment

    def _form_changed(self, form: str) -> None:
        if not self._refreshing and self.document is not None:
            if form == "role":
                self.pending_role = True
            else:
                self.pending_segment = True
            self.dirty = True
            self._changed()

    def _dialogue_changed(self, event: tk.Event) -> None:
        if self.dialogue.edit_modified():
            self._form_changed("segment")
            self.dialogue.edit_modified(False)

    def set_document(self, document: ConversationDocument) -> None:
        """Swap only a successfully validated document on the main thread."""
        if self.document is None or self.document.document_id != document.document_id:
            self.project_assignments = {}
            self.preferences = {}
            self.mappings = MappingState()
        self.document = document
        self.mappings.reconcile(document)
        self.dirty = False
        self.pending_role = False
        self.pending_segment = False
        self._role_key = None
        self._segment_key = None
        self.refresh()
        self._changed()

    def configure_provider(
        self,
        choice: ProviderChoice,
        *,
        locale: str = "en-US",
        job_speed: float | None = None,
        file_presence: dict[str, bool] | None = None,
        suggestions: tuple[str, ...] | None = None,
    ) -> None:
        """Refresh suggestions without rewriting identity-keyed assignments."""
        self._choice = choice
        self._locale = locale
        self._job_speed = job_speed
        self._file_presence = file_presence or {}
        self.voice_box.configure(
            values=suggestions
            if suggestions is not None
            else tuple(v.voice_id for v in choice.voices),
            state="normal" if choice.provider_id == "edge" else "readonly",
        )
        self.refresh()

    def preflight(self) -> Preflight:
        """Return the same metadata resolution consumed by the service."""
        if self.document is None or self._choice is None:
            raise ValueError("Open a JSON conversation first.")
        return resolve_document(
            self.document,
            self._choice,
            current=self.mappings.selections(self.document, self._choice.provider_id),
            project=self.project_assignments.get(self._choice.provider_id),
            preferences=self.preferences,
            locale=self._locale,
            job_speed=self._job_speed,
            file_present=lambda model: self._file_presence.get(model, False),
        )

    def refresh(self) -> None:
        """Render lists with stable role IDs and ordered segment indices."""
        if self.document is None or self._choice is None:
            return
        role_selection = self.roles.selection()
        segment_selection = self.segments.selection()
        result = self.preflight()
        for tree in (self.roles, self.segments, self.diagnostics):
            tree.delete(*tree.get_children())
        for speaker, assignment in zip(
            self.document.speakers, result.assignments, strict=True
        ):
            self.roles.insert(
                "",
                "end",
                iid=speaker.id,
                text=f"{speaker.role} ({speaker.id}) — {assignment.voice_id}",
            )
        labels = tuple(
            f"{speaker.role} ({speaker.id})" for speaker in self.document.speakers
        )
        self.speaker_box.configure(values=labels)
        for index, segment in enumerate(self.document.segments):
            self.segments.insert(
                "",
                "end",
                iid=str(index),
                text=f"{index + 1}. {segment.speaker}: {' '.join(segment.text.split())[:90]} | after {segment.pause_after_seconds:g}s",
            )
        self._diagnostic_paths.clear()
        for index, issue in enumerate(result.diagnostics):
            key = str(index)
            self.diagnostics.insert(
                "",
                "end",
                iid=key,
                text=f"{issue.severity}: {issue.path}: {issue.message}",
            )
            self._diagnostic_paths[key] = issue.path
        self._summary.set(
            f"{result.role_count} roles ({result.used_role_count} used) · "
            f"{len(result.segments)} segments · {result.word_count} words · "
            f"{result.silence_seconds:g}s explicit silence · final "
            f"{result.segments[-1].pause_after_seconds:g}s · {len(result.errors)} errors. "
            "Directions are notes; only structured speed is applied where supported."
        )
        self.roles.selection_set(
            role_selection[0]
            if role_selection and self.roles.exists(role_selection[0])
            else self.document.speakers[0].id
        )
        self.segments.selection_set(
            segment_selection[0]
            if segment_selection and self.segments.exists(segment_selection[0])
            else "0"
        )
        self._select_role()
        self._select_segment()

    def _confirm_pending(self) -> bool:
        if not self.pending:
            return True
        return messagebox.askyesno(
            "Unapplied edits",
            "Discard unapplied form edits? Use Apply role/segment to retain them.",
        )

    def _select_role(self, event: tk.Event | None = None) -> None:
        if self.document is None or not self.roles.selection():
            return
        key = self.roles.selection()[0]
        if self.pending_role:
            if key == self._role_key:
                return
            if not self._confirm_pending():
                self.roles.selection_set(self._role_key)
                return
            self.pending_role = False
        self._role_key = key
        speaker = next(item for item in self.document.speakers if item.id == key)
        assignment = next(
            item for item in self.preflight().assignments if item.speaker_id == key
        )
        self._refreshing = True
        try:
            self.role_name.set(speaker.role)
            self.role_voice.set(assignment.voice_id)
            self.role_speed.set(
                "" if speaker.speech.speed is None else str(speaker.speech.speed)
            )
            self.role_note.set(speaker.voice_direction)
            metadata = next(
                (
                    voice
                    for voice in self._choice.voices
                    if voice.voice_id == assignment.voice_id
                ),
                None,
            )
            segment = next(
                (
                    item
                    for item in self.preflight().segments
                    if item.speaker_id == speaker.id
                ),
                None,
            )
            locale = metadata.language if metadata else "Custom voice"
            model = metadata.model_id if metadata and metadata.model_id else "Online"
            effective = (
                f"speed {segment.speed} ({segment.speed_source})"
                if segment
                else "No dialogue"
            )
            self.role_info.set(
                f"ID: {speaker.id} · {assignment.origin} · {locale} · {model} · "
                f"{assignment.readiness} · {effective}"
            )
        finally:
            self._refreshing = False

    def _select_segment(self, event: tk.Event | None = None) -> None:
        if self.document is None or not self.segments.selection():
            return
        key = self.segments.selection()[0]
        if self.pending_segment:
            if key == self._segment_key:
                return
            if not self._confirm_pending():
                self.segments.selection_set(self._segment_key)
                return
            self.pending_segment = False
        self._segment_key = key
        segment = self.document.segments[int(key)]
        speaker = next(
            item for item in self.document.speakers if item.id == segment.speaker
        )
        self._refreshing = True
        try:
            self.segment_speaker.set(f"{speaker.role} ({speaker.id})")
            self.segment_pause.set(str(segment.pause_after_seconds))
            self.segment_speed.set(
                "" if segment.speech.speed is None else str(segment.speech.speed)
            )
            self.segment_note.set(segment.voice_direction)
            self.dialogue.delete("1.0", "end")
            self.dialogue.insert("1.0", segment.text)
            self.dialogue.edit_modified(False)
        finally:
            self._refreshing = False

    @staticmethod
    def _set_speed(record: dict, value: str) -> None:
        speech = record.setdefault("speech", {})
        if value.strip():
            speech["speed"] = float(value)
        else:
            speech.pop("speed", None)

    def apply_role(self) -> bool:
        """Validate a role edit atomically, retaining extensions."""
        if self.document is None or not self.roles.selection() or self._choice is None:
            return False
        key = self.roles.selection()[0]
        data = self.document.to_dict()
        role = next(item for item in data["speakers"] if item["id"] == key)
        role["role"] = self.role_name.get()
        role["voice_direction"] = self.role_note.get()
        try:
            self._set_speed(role, self.role_speed.get())
            edited = self.document.with_data(data)
        except ValueError as error:
            messagebox.showerror("Invalid role", str(error))
            return False
        self.mappings.set_voice(
            edited, key, self._choice.provider_id, self.role_voice.get()
        )
        self.document = edited
        self.pending_role = False
        self._applied()
        return True

    def apply_segment(self) -> bool:
        """Validate a complete segment edit before replacing the snapshot."""
        if self.document is None or not self.segments.selection():
            return False
        data = self.document.to_dict()
        segment = data["segments"][int(self.segments.selection()[0])]
        labels = {
            f"{speaker.role} ({speaker.id})": speaker.id
            for speaker in self.document.speakers
        }
        try:
            segment["speaker"] = labels[self.segment_speaker.get()]
            segment["text"] = self.dialogue.get("1.0", "end-1c")
            segment["pause_after_seconds"] = float(self.segment_pause.get())
            segment["voice_direction"] = self.segment_note.get()
            self._set_speed(segment, self.segment_speed.get())
            edited = self.document.with_data(data)
        except (KeyError, ValueError) as error:
            messagebox.showerror("Invalid segment", str(error))
            return False
        self.document = edited
        self.pending_segment = False
        self._applied()
        return True

    def _applied(self) -> None:
        self.dirty = True
        self.refresh()
        self._changed()

    def reset_role(self) -> None:
        """Reset selected voice without overwriting another role."""
        if self.document and self._choice and self.roles.selection():
            self.pending_role = False
            self.project_assignments.get(self._choice.provider_id, {}).pop(
                self.roles.selection()[0], None
            )
            self.mappings.reset_role(
                self.document, self.roles.selection()[0], self._choice.provider_id
            )
            self._applied()

    def _select_diagnostic(self, event: tk.Event) -> None:
        if not self.diagnostics.selection():
            return
        path = self._diagnostic_paths[self.diagnostics.selection()[0]]
        match = re.search(r"\.(speakers|segments)\[(\d+)\]", path)
        if match and self.document:
            kind, index = match.group(1), int(match.group(2))
            tree = self.roles if kind == "speakers" else self.segments
            key = self.document.speakers[index].id if kind == "speakers" else str(index)
            self.tabs.select(0 if kind == "speakers" else 1)
            tree.selection_set(key)
            tree.see(key)
            tree.focus_set()

    def preview_segment(self) -> ResolvedSegment:
        """Select actual role dialogue with its effective speed; omit pauses."""
        result = self.preflight()
        selected_role = self.roles.selection()[0]
        selected_index = int(self.segments.selection()[0]) + 1
        candidates = [
            item for item in result.segments if item.speaker_id == selected_role
        ]
        if not candidates:
            raise ValueError("This role has no dialogue to preview.")
        segment = next(
            (item for item in candidates if item.index == selected_index), candidates[0]
        )
        role_index = next(
            index
            for index, role in enumerate(self.document.speakers)
            if role.id == selected_role
        )
        paths = (f"$.speakers[{role_index}]", f"$.segments[{segment.index - 1}]")
        errors = tuple(item for item in result.errors if item.path.startswith(paths))
        if errors:
            raise DocumentValidationError(errors)
        return segment
