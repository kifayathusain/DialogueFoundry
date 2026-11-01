"""Windows desktop UI for the TTS app (M02).

Built with Tkinter (part of the Python standard library, no extra
dependency needed) so the app can run as a plain desktop window without a
developer workflow.

The UI only handles input collection, validation, threading and rendering
progress/results. All TTS/FFmpeg work is delegated to
:func:`ttsapp.service.generate_conversation`, so this module does not
duplicate any pipeline logic.

Plain functions (``validate_script_text``, ``build_speaker_voice_mapping``) are
kept free of Tkinter so they can be unit tested without a display.
"""

import asyncio
import os
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass, replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .audio_combiner import FFmpegExecutionError, FFmpegNotFoundError
from .audio_export import validate_export_target
from .config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_FINAL_AUDIO,
    DEFAULT_OUTPUT_DIR,
    VOICES,
)
from .conversation_document import ConversationDocument, load_document, save_document_as
from .desktop_options import (
    DesktopGenerationOptions,
    build_desktop_options,
    build_export_settings,
    filter_voice_choices,
)
from .model_library import ModelLibraryWindow
from .parser import ConversationLine
from .preview import PreviewService, WindowsAudioPlayer, strip_speaker_labels
from .project_storage import (
    ProjectSnapshot,
    load_project,
    new_project,
    preset_from_data,
    read_json_file,
    save_preset,
    save_project,
)
from .provider_manager import ProviderManager
from .providers.base import CancellationToken
from .service import generate_conversation
from .speaker_mapping import MappingState
from .structured_editor import StructuredEditor
from .text_processing import SpeechChunk
from .tts_engine import TTSGenerationError

APP_TITLE = f"{APP_NAME} {APP_VERSION}"


def default_desktop_output_path() -> Path:
    """Return a writable, predictable output location independent of the CWD."""

    return Path.home() / "Documents" / APP_NAME / DEFAULT_FINAL_AUDIO


def format_generation_error(error: Exception) -> str:
    """Add plain-language recovery steps to common generation errors."""

    if isinstance(error, FFmpegNotFoundError):
        return (
            "FFmpeg is required to combine the generated speech. Install FFmpeg, "
            "add ffmpeg.exe to PATH, then restart the app. Verify the installation "
            "with `ffmpeg -version`. Validated exports also require ffprobe.exe "
            "on PATH."
        )
    if isinstance(error, FFmpegExecutionError):
        return (
            "The speech was generated, but FFmpeg could not combine the audio. "
            "Check that FFmpeg is installed and that the generated files are "
            "available, then try again.\n\n"
            f"Details: {error}"
        )
    if isinstance(error, PermissionError):
        return (
            "The app could not save to the selected location. Choose a folder "
            "where your account has write permission.\n\n"
            f"Details: {error}"
        )
    if isinstance(error, TTSGenerationError):
        return (
            "Speech generation failed. Check your internet connection and the "
            "selected Edge TTS voice, then try again.\n\n"
            f"Details: {error}"
        )
    return str(error)


def validate_script_text(text: str) -> None:
    """Raise ``ValueError`` if ``text`` has no usable conversation content."""

    if not text or not text.strip():
        raise ValueError("Please enter or paste some conversation text first.")


def build_speaker_voice_mapping(
    speaker_rows: list[tuple[str, str]],
) -> dict[str, str]:
    """Validate editable speaker names and their selected Edge TTS voices."""

    voices = {}
    for index, (speaker, voice) in enumerate(speaker_rows, start=1):
        speaker = speaker.strip()
        voice = voice.strip()
        if not speaker and not voice:
            continue
        if not speaker:
            raise ValueError(f"Please enter a name for Speaker {index}.")
        if not voice:
            raise ValueError(f"Please enter an Edge TTS voice for '{speaker}'.")
        if speaker in voices:
            raise ValueError(f"Speaker name '{speaker}' is used more than once.")
        voices[speaker] = voice

    if not voices:
        raise ValueError("Configure at least one speaker name and voice.")

    return voices


@dataclass(frozen=True)
class _ProgressMessage:
    """Internal message passed from the worker thread to the UI thread."""

    kind: str
    index: int = 0
    total: int = 0
    speaker: str = ""
    final_audio: Path | None = None
    path: Path | None = None
    revision: int = 0
    message: str = ""
    document: ConversationDocument | None = None
    project: ProjectSnapshot | None = None
    preferences: tuple[tuple[tuple[str, str, str], str], ...] = ()


class TTSDesktopApp(tk.Tk):
    """Tkinter input/rendering with worker-owned synthesis, previews, and sessions."""

    POLL_INTERVAL_MS = 100

    def __init__(self, providers: ProviderManager | None = None) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("800x760")
        self.minsize(480, 360)
        self._provider_manager = (
            providers if providers is not None else ProviderManager()
        )
        self._choices = {
            choice.provider_id: choice
            for choice in self._provider_manager.list_choices()
        }
        self._choice_names = {
            choice.display_name: choice.provider_id for choice in self._choices.values()
        }
        self._provider_id = "edge"
        self._saved_chunk_limit = 1000
        self._saved_export_timeout = 600.0
        self._project_id: str | None = None
        self._source_locator: str | None = None
        self._source_sha256: str | None = None
        self._provider_var = tk.StringVar(value=self._choices["edge"].display_name)
        self._language_var = tk.StringVar(value="All languages")
        self._voice_search_var = tk.StringVar()
        self._voice_details: list[tk.StringVar] = []
        self._provider_status = tk.StringVar()
        self._speed_var = tk.StringVar(value="1.0")
        self._process_text_var = tk.BooleanVar(value=False)
        self._edge_processing = False
        self._sentence_pause_var = tk.StringVar(value="0.0")
        self._paragraph_pause_var = tk.StringVar(value="0.35")
        self._format_var = tk.StringVar(value="MP3")
        self._bitrate_var = tk.StringVar(value="Auto")
        self._sample_rate_var = tk.StringVar(value="Native")
        self._channels_var = tk.StringVar(value="Source")
        self._normalize_var = tk.BooleanVar(value=False)
        self._speaker_rows: list[tuple[tk.StringVar, tk.StringVar]] = []
        self._speaker_entries: list[ttk.Entry] = []
        self._voice_boxes: list[ttk.Combobox] = []
        self._preview_buttons: list[ttk.Button] = []
        self._voice_selections: dict[str, tuple[str, ...]] = {}
        self._output_path_var = tk.StringVar(value=str(default_desktop_output_path()))
        self._status_var = tk.StringVar(value="Ready.")
        self._count_var = tk.StringVar(value="0 words · 0 characters")
        self._elapsed_var = tk.StringVar(value="")
        self._queue: queue.Queue[_ProgressMessage] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._model_library: ModelLibraryWindow | None = None
        self._cancellation_token = CancellationToken()
        self._preview_service = PreviewService(self._provider_manager)
        self._player = WindowsAudioPlayer()
        self._last_preview: Path | None = None
        self._preview_revision = 0
        self._busy = False
        self._closing = False
        self._shutdown_started = False
        self._operation_kind = ""
        self._started_at = 0.0
        self._chunk_progress_active = False
        self._exporting = False
        self._build_widgets()
        self._provider_changed()
        for variable in (
            self._provider_var,
            self._language_var,
            self._speed_var,
            self._process_text_var,
            self._sentence_pause_var,
            self._paragraph_pause_var,
            self._format_var,
            self._bitrate_var,
            self._sample_rate_var,
            self._channels_var,
            self._normalize_var,
        ):
            variable.trace_add("write", lambda *args: self._settings_changed())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(self.POLL_INTERVAL_MS, self._drain_queue)

    def _build_widgets(self) -> None:
        # Keep action/status controls outside the scrollable editing surface.
        surface = ttk.Frame(self)
        surface.pack(fill="both", expand=True)
        canvas = tk.Canvas(surface, highlightthickness=0)
        self._scroll_canvas = canvas
        vertical = ttk.Scrollbar(
            surface, orient="vertical", command=canvas.yview, takefocus=True
        )
        horizontal = ttk.Scrollbar(
            self, orient="horizontal", command=canvas.xview, takefocus=True
        )
        canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        horizontal.pack(fill="x")
        self._content = ttk.Frame(canvas)
        item = canvas.create_window((0, 0), window=self._content, anchor="nw")
        self._content.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(item, width=max(720, event.width)),
        )
        self.bind("<FocusIn>", self._reveal_focus)
        self._build_text_editor()
        self._build_provider_controls()
        self._build_speaker_controls()
        self._build_processing_controls()
        self._build_export_controls()
        self._build_output_controls()
        self._build_actions()

    def _build_text_editor(self) -> None:
        file_bar = ttk.Frame(self._content)
        file_bar.pack(fill="x", padx=10, pady=4)
        ttk.Button(
            file_bar, text="Open / Import", command=self._open_conversation
        ).pack(side="left")
        ttk.Button(file_bar, text="JSON Save As", command=self._save_json_as).pack(
            side="left", padx=4
        )
        project_bar = ttk.Frame(self._content)
        project_bar.pack(fill="x", padx=10, pady=4)
        for label, command in (
            ("Open project", self._open_project),
            ("Save project As", self._save_project_as),
            ("Save mapping preset", self._save_mapping_preset),
            ("Apply preset", self._apply_mapping_preset),
        ):
            ttk.Button(project_bar, text=label, command=command).pack(
                side="left", padx=2
            )
        self._mode_tabs = ttk.Notebook(self._content)
        self._mode_tabs.pack(fill="both", expand=True, padx=10)
        plain = ttk.Frame(self._mode_tabs)
        self._mode_tabs.add(plain, text="Plain text")
        self.structured = StructuredEditor(
            self._mode_tabs, self._structured_changed, self._preview_structured
        )
        self._mode_tabs.add(self.structured, text="JSON")
        self._mode_tabs.enable_traversal()
        self._mode_tabs.bind("<<NotebookTabChanged>>", self._mode_changed)
        toolbar = ttk.Frame(plain)
        toolbar.pack(fill="x", padx=10, pady=6)
        ttk.Label(toolbar, text="Conversation script: Speaker: text").pack(side="left")
        ttk.Button(toolbar, text="Paste", command=self._paste_text).pack(
            side="left", padx=8
        )
        ttk.Button(
            toolbar, text="Clear", command=lambda: self.text_box.delete("1.0", "end")
        ).pack(side="left")
        ttk.Label(toolbar, textvariable=self._count_var).pack(side="right")
        frame = ttk.Frame(plain)
        frame.pack(fill="both", expand=True, padx=10)
        self.text_box = tk.Text(frame, wrap="word", height=10, undo=True)
        scrollbar = ttk.Scrollbar(frame, command=self.text_box.yview)
        self.text_box.configure(yscrollcommand=scrollbar.set)
        self.text_box.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.text_box.bind("<<Modified>>", self._text_modified)

    def _build_provider_controls(self) -> None:
        frame = ttk.Frame(self._content)
        frame.pack(fill="x", padx=10, pady=6)
        ttk.Label(frame, text="Provider:").pack(side="left")
        self._provider_box = ttk.Combobox(
            frame,
            textvariable=self._provider_var,
            values=tuple(self._choice_names),
            state="readonly",
            width=22,
        )
        self._provider_box.pack(side="left", padx=6)
        self._provider_box.bind(
            "<<ComboboxSelected>>", lambda event: self._provider_changed()
        )
        ttk.Label(frame, text="Language/accent:").pack(side="left")
        self._language_box = ttk.Combobox(
            frame, textvariable=self._language_var, state="readonly", width=14
        )
        self._language_box.pack(side="left", padx=6)
        self._language_box.bind(
            "<<ComboboxSelected>>", lambda event: self._filter_voices()
        )
        self._model_library_button = ttk.Button(
            frame, text="Model library...", command=self._open_model_library
        )
        self._model_library_button.pack(side="right")
        ttk.Label(
            self._content, textvariable=self._provider_status, wraplength=760
        ).pack(fill="x", padx=10)
        search_frame = ttk.Frame(self._content)
        search_frame.pack(fill="x", padx=10)
        ttk.Label(search_frame, text="Search voices / quality / speaker:").pack(
            side="left"
        )
        self._voice_search = ttk.Entry(
            search_frame, textvariable=self._voice_search_var
        )
        self._voice_search.pack(side="left", fill="x", expand=True, padx=6)
        self._filter_after = None
        self._voice_search_var.trace_add("write", lambda *args: self._schedule_filter())

    def _build_speaker_controls(self) -> None:
        frame = ttk.LabelFrame(self._content, text="Speakers and voices")
        self._legacy_speaker_frame = frame
        frame.pack(fill="x", padx=10, pady=6)
        for index, (speaker, voice) in enumerate(VOICES.items()):
            speaker_var = tk.StringVar(value=speaker)
            voice_var = tk.StringVar(value=voice)
            self._speaker_rows.append((speaker_var, voice_var))
            ttk.Label(frame, text=f"Speaker {index + 1}").grid(
                row=index * 2, column=0, padx=6, pady=4
            )
            entry = ttk.Entry(frame, textvariable=speaker_var, width=20)
            entry.grid(row=index * 2, column=1, padx=4, pady=4, sticky="ew")
            self._speaker_entries.append(entry)
            voice_box = ttk.Combobox(frame, textvariable=voice_var, width=29)
            voice_box.grid(row=index * 2, column=2, padx=4, pady=4, sticky="ew")
            self._voice_boxes.append(voice_box)
            button = ttk.Button(
                frame,
                text="Preview",
                command=lambda slot=index: self._on_preview_clicked(slot),
            )
            button.grid(row=index * 2, column=3, padx=6, pady=4)
            self._preview_buttons.append(button)
            detail = tk.StringVar()
            self._voice_details.append(detail)
            ttk.Label(frame, textvariable=detail, wraplength=700).grid(
                row=index * 2 + 1, column=0, columnspan=4, sticky="w", padx=6
            )
            voice_var.trace_add("write", lambda *args: self._voice_changed())
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=2)
        self._legacy_hint = ttk.Label(
            self._content,
            text="Select text and click a speaker's Preview, or preview a sample (up to 400 characters).",
        )
        self._legacy_hint.pack(anchor="w", padx=10)

    def _build_processing_controls(self) -> None:
        frame = ttk.Frame(self._content)
        self._processing_frame = frame
        frame.pack(fill="x", padx=10, pady=6)
        ttk.Label(frame, text="Speed:").pack(side="left")
        self._speed_control = ttk.Spinbox(
            frame,
            textvariable=self._speed_var,
            from_=0.5,
            to=2.0,
            increment=0.1,
            width=5,
        )
        self._speed_control.pack(side="left", padx=5)
        self._process_control = ttk.Checkbutton(
            frame,
            text="Process text / pauses",
            variable=self._process_text_var,
            command=self._apply_control_states,
        )
        self._process_control.pack(side="left", padx=6)
        ttk.Label(frame, text="Sentence pause (s):").pack(side="left")
        self._sentence_control = ttk.Spinbox(
            frame,
            textvariable=self._sentence_pause_var,
            from_=0,
            to=5,
            increment=0.05,
            width=5,
        )
        self._sentence_control.pack(side="left", padx=5)
        ttk.Label(frame, text="Paragraph (s):").pack(side="left")
        self._paragraph_control = ttk.Spinbox(
            frame,
            textvariable=self._paragraph_pause_var,
            from_=0,
            to=5,
            increment=0.05,
            width=5,
        )
        self._paragraph_control.pack(side="left", padx=5)

    def _build_export_controls(self) -> None:
        self._advanced_export = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self._content,
            text="Advanced export options",
            variable=self._advanced_export,
            command=self._toggle_export_options,
        ).pack(anchor="w", padx=10)
        frame = ttk.LabelFrame(self._content, text="Audio export")
        self._export_frame = frame
        frame.pack(fill="x", padx=10, pady=4)
        ttk.Label(frame, text="Format:").grid(row=0, column=0, padx=6, pady=4)
        self._format_box = ttk.Combobox(
            frame,
            textvariable=self._format_var,
            values=("MP3", "WAV", "M4A"),
            width=7,
            state="readonly",
        )
        self._format_box.grid(row=0, column=1, padx=4, pady=4)
        self._format_box.bind(
            "<<ComboboxSelected>>", lambda event: self._export_format_changed()
        )
        ttk.Label(frame, text="MP3 bitrate (kbps):").grid(row=0, column=2, padx=6)
        self._bitrate_box = ttk.Combobox(
            frame,
            textvariable=self._bitrate_var,
            values=("Auto", "64", "96", "128", "160", "192", "256", "320"),
            width=8,
            state="readonly",
        )
        self._bitrate_box.grid(row=0, column=3, padx=4)
        self._normalize_control = ttk.Checkbutton(
            frame, text="Normalize loudness", variable=self._normalize_var
        )
        self._normalize_control.grid(row=0, column=4, padx=10)
        ttk.Label(frame, text="Sample rate:").grid(row=1, column=0, padx=6, pady=4)
        self._sample_rate_box = ttk.Combobox(
            frame,
            textvariable=self._sample_rate_var,
            values=("Native", "16000", "22050", "24000", "32000", "44100", "48000"),
            width=7,
            state="readonly",
        )
        self._sample_rate_box.grid(row=1, column=1, padx=4, pady=4)
        ttk.Label(frame, text="Channels:").grid(row=1, column=2, padx=6)
        self._channels_box = ttk.Combobox(
            frame,
            textvariable=self._channels_var,
            values=("Source", "Mono", "Stereo"),
            width=8,
            state="readonly",
        )
        self._channels_box.grid(row=1, column=3, padx=4)

        frame.pack_forget()

    def _toggle_export_options(self) -> None:
        if self._advanced_export.get():
            self._export_frame.pack(
                fill="x", padx=10, pady=4, before=self._output_frame
            )
        else:
            self._export_frame.pack_forget()

    def _export_format_changed(self) -> None:
        output = self._output_path_var.get().strip() or str(
            default_desktop_output_path()
        )
        self._output_path_var.set(
            str(Path(output).with_suffix(f".{self._format_var.get().lower()}"))
        )
        self._apply_control_states()

    def _build_output_controls(self) -> None:
        frame = ttk.Frame(self._content)
        self._output_frame = frame
        frame.pack(fill="x", padx=10, pady=6)
        ttk.Label(frame, text="Output file:").pack(side="left")
        ttk.Entry(frame, textvariable=self._output_path_var).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(frame, text="Browse...", command=self._choose_output_path).pack(
            side="left"
        )
        ttk.Button(frame, text="Open folder", command=self._open_output_folder).pack(
            side="left", padx=6
        )

    def _build_actions(self) -> None:
        frame = ttk.Frame(self)
        frame.pack(fill="x", padx=10, pady=6)
        self.generate_button = ttk.Button(
            frame, text="Generate", command=self._on_generate_clicked
        )
        self.generate_button.pack(side="left")
        self._cancel_button = ttk.Button(
            frame, text="Cancel", command=self._cancel_work
        )
        self._cancel_button.pack(side="left", padx=6)
        self._replay_button = ttk.Button(
            frame, text="Play / Replay", command=self._replay_preview
        )
        self._replay_button.pack(side="left")
        ttk.Button(frame, text="Stop", command=self._stop_playback).pack(
            side="left", padx=6
        )
        self.progress_bar = ttk.Progressbar(
            frame, mode="determinate", maximum=1, value=0
        )
        self.progress_bar.pack(side="left", fill="x", expand=True)
        ttk.Label(self, textvariable=self._status_var, wraplength=760).pack(
            fill="x", padx=10, pady=4
        )
        ttk.Label(self, textvariable=self._elapsed_var).pack(
            anchor="w", padx=10, pady=(0, 6)
        )

    def _text_modified(self, event: tk.Event) -> None:
        if self.text_box.edit_modified():
            text = self.text_box.get("1.0", "end-1c")
            self._count_var.set(f"{len(text.split())} words · {len(text)} characters")
            self.text_box.edit_modified(False)
            self._invalidate_preview()

    def _paste_text(self) -> None:
        try:
            self.text_box.insert("insert", self.clipboard_get())
        except tk.TclError:
            self._status_var.set("The clipboard does not contain text.")

    def _provider_changed(self) -> None:
        if (
            "structured" in self.__dict__
            and self.structured.pending_role
            and not self.structured.apply_role()
        ):
            self._provider_var.set(self._choices[self._provider_id].display_name)
            return
        if self._provider_id == "edge":
            self._edge_processing = self._process_text_var.get()
        self._voice_selections[self._provider_id] = tuple(
            voice.get() for speaker, voice in self._speaker_rows
        )
        self._provider_id = self._choice_names[self._provider_var.get()]
        choice = self._choices[self._provider_id]
        self._process_text_var.set(self._edge_processing if choice.online else True)
        previous = self._voice_selections.get(self._provider_id)
        for index, (_speaker, voice) in enumerate(self._speaker_rows):
            if previous is not None:
                voice.set(previous[index])
            else:
                voice.set(choice.voices[index % len(choice.voices)].voice_id)
        languages = tuple(sorted({voice.language for voice in choice.voices}))
        self._language_box.configure(values=("All languages", *languages))
        self._language_var.set("All languages")
        self._voice_search_var.set("")
        self._filter_voices()
        if choice.online:
            self._provider_status.set(
                "Online · Edge sends the script to Microsoft's service. FFmpeg is required."
            )
        else:
            model = self._provider_manager.models.manifest(choice.model_id)
            self._provider_status.set(
                f"Offline CPU · {model.runtime}. Install/verify assets in Model library."
            )
        self._apply_control_states()
        self._invalidate_preview()
        self._sync_structured_provider()

    def _schedule_filter(self) -> None:
        if self._filter_after is not None:
            self.after_cancel(self._filter_after)
        self._filter_after = self.after(150, self._filter_voices)

    def _reveal_focus(self, event: tk.Event) -> None:
        widget = event.widget
        ancestor = widget
        while ancestor is not None and ancestor is not self._content:
            ancestor = getattr(ancestor, "master", None)
        if ancestor is None:
            return
        canvas = self._scroll_canvas
        width = max(1, self._content.winfo_width())
        height = max(1, self._content.winfo_height())
        x = widget.winfo_rootx() - self._content.winfo_rootx()
        y = widget.winfo_rooty() - self._content.winfo_rooty()
        if y < canvas.canvasy(0) or y + widget.winfo_height() > canvas.canvasy(
            canvas.winfo_height()
        ):
            canvas.yview_moveto(max(0, y - 10) / height)
        if x < canvas.canvasx(0) or x + widget.winfo_width() > canvas.canvasx(
            canvas.winfo_width()
        ):
            canvas.xview_moveto(max(0, x - 10) / width)

    def _filter_voices(self) -> None:
        self._filter_after = None
        choice = self._choices[self._provider_id]
        language = self._language_var.get()
        values = tuple(
            voice.voice_id
            for voice in filter_voice_choices(
                choice, language, self._voice_search_var.get()
            )
        )
        for box in self._voice_boxes:
            box.configure(values=values)
        self._sync_structured_provider(values)

    def _voice_changed(self) -> None:
        """Describe selected assets cheaply; full verification happens in workers."""
        self._invalidate_preview()
        voices = {
            voice.voice_id: voice for voice in self._choices[self._provider_id].voices
        }
        for (_, selected), detail in zip(
            self._speaker_rows, self._voice_details, strict=True
        ):
            voice = voices.get(selected.get())
            if voice is None:
                detail.set("")
                continue
            if voice.model_id is None or self._provider_id == "edge":
                detail.set(voice.display_name)
                continue
            model = self._provider_manager.models.manifest(voice.model_id)
            directory = self._provider_manager.models.model_directory(model.model_id)
            present = all(
                (directory / asset.filename).is_file() for asset in model.files
            )
            status = "Files present; verified on use" if present else "Not installed"
            detail.set(
                f"{voice.display_name} · {status} · Model library: {model.model_id}"
            )

    def _apply_control_states(self) -> None:
        choice = self._choices[self._provider_id]
        state = "disabled" if self._busy or self._closing else "normal"
        self._provider_box.configure(
            state="disabled" if self._busy or self._closing else "readonly"
        )
        self._language_box.configure(
            state="disabled" if self._busy or self._closing else "readonly"
        )
        self._model_library_button.configure(state=state)
        self._voice_search.configure(state=state)
        for entry in self._speaker_entries:
            entry.configure(state=state)
        for box in self._voice_boxes:
            box.configure(
                state="disabled"
                if self._busy or self._closing
                else ("normal" if choice.online else "readonly")
            )
        for button in self._preview_buttons:
            button.configure(state=state)
        self._speed_control.configure(
            state=state if choice.supports_speed else "disabled"
        )
        json_mode = "structured" in self.__dict__ and self._json_mode()
        self._process_control.configure(
            state=state if choice.online and not json_mode else "disabled"
        )
        processing = json_mode or self._process_text_var.get() or not choice.online
        self._sentence_control.configure(state=state if processing else "disabled")
        self._paragraph_control.configure(
            state=state if processing and not json_mode else "disabled"
        )
        self._replay_button.configure(
            state=state if self._last_preview is not None else "disabled"
        )
        export_state = "disabled" if self._busy or self._closing else "readonly"
        self._format_box.configure(state=export_state)
        self._sample_rate_box.configure(state=export_state)
        self._channels_box.configure(state=export_state)
        self._bitrate_box.configure(
            state=export_state if self._format_var.get() == "MP3" else "disabled"
        )
        self._normalize_control.configure(state=state)

    def _read_voice_options(self) -> DesktopGenerationOptions:
        return build_desktop_options(
            self._choices[self._provider_id],
            self._speed_var.get(),
            self._process_text_var.get()
            or ("structured" in self.__dict__ and self._json_mode()),
            self._sentence_pause_var.get(),
            self._paragraph_pause_var.get(),
        )

    def _read_options(self) -> DesktopGenerationOptions:
        options = self._read_voice_options()
        settings = build_export_settings(
            self._format_var.get().lower(),
            self._bitrate_var.get(),
            self._sample_rate_var.get(),
            self._channels_var.get(),
            self._normalize_var.get(),
        )
        if "structured" in self.__dict__ and self._json_mode():
            from .text_processing import TextProcessingSettings

            processing = options.text_settings or TextProcessingSettings()
            options = replace(
                options,
                text_settings=replace(
                    processing, max_chunk_characters=self._saved_chunk_limit
                ),
            )
            settings = replace(settings, timeout_seconds=self._saved_export_timeout)
        return replace(options, export_settings=settings)

    def _open_model_library(self) -> None:
        self._invalidate_preview()
        if self._model_library is None or not self._model_library.winfo_exists():
            self._model_library = ModelLibraryWindow(
                self, self._provider_manager.models, self._provider_manager.close
            )
            self._model_library.bind("<Destroy>", self._library_closed, add="+")
        else:
            self._model_library.lift()

    def _library_closed(self, event: tk.Event) -> None:
        """Refresh asset presence after the library's worker has finished cleanup."""
        if event.widget is self._model_library and not self._closing:
            self._voice_changed()

    def _choose_output_path(self) -> None:
        chosen = filedialog.asksaveasfilename(
            title="Choose output audio file",
            defaultextension=f".{self._format_var.get().lower()}",
            filetypes=[
                ("MP3 audio", "*.mp3"),
                ("WAV audio", "*.wav"),
                ("M4A audio", "*.m4a"),
            ],
            initialfile=Path(self._output_path_var.get()).name,
        )
        if chosen:
            self._output_path_var.set(chosen)
            suffix = Path(chosen).suffix.lower()
            if suffix in {".mp3", ".wav", ".m4a"}:
                self._format_var.set(suffix[1:].upper())
                self._apply_control_states()

    def _open_output_folder(self) -> None:
        directory = Path(
            self._output_path_var.get().strip() or str(default_desktop_output_path())
        ).parent
        try:
            directory.mkdir(parents=True, exist_ok=True)
            os.startfile(directory)
        except OSError as error:
            messagebox.showerror(APP_TITLE, str(error))

    def _begin_work(self, operation: str) -> None:
        self._player.stop()
        self._cancellation_token = CancellationToken()
        self._operation_kind = operation
        self._chunk_progress_active = False
        self._exporting = False
        self._started_at = time.monotonic()
        self._set_busy(True)
        self._status_var.set(
            "Generating..."
            if operation == "generation"
            else "Generating voice preview..."
        )
        self.progress_bar.configure(value=0, maximum=1)

    def _mode_changed(self, event: tk.Event) -> None:
        self._invalidate_preview()
        self._apply_control_states()
        if self._json_mode():
            self._legacy_speaker_frame.pack_forget()
            self._legacy_hint.pack_forget()
        else:
            self._legacy_speaker_frame.pack(
                fill="x", padx=10, pady=6, before=self._processing_frame
            )
            self._legacy_hint.pack(anchor="w", padx=10, before=self._processing_frame)

    def _json_mode(self) -> bool:
        return self._mode_tabs.select() == str(self.structured)

    def _settings_changed(self) -> None:
        self._invalidate_preview()
        if self.structured.document is not None:
            self.structured.dirty = True

    def _structured_changed(self) -> None:
        self._invalidate_preview()

    def _sync_structured_provider(
        self, suggestions: tuple[str, ...] | None = None
    ) -> None:
        if "structured" not in self.__dict__:
            return
        choice = self._choices[self._provider_id]
        try:
            speed = float(self._speed_var.get()) if choice.supports_speed else None
        except ValueError:
            speed = None
        locale = self._language_var.get()
        presence = {}
        for model_id in {voice.model_id for voice in choice.voices if voice.model_id}:
            model = self._provider_manager.models.manifest(model_id)
            directory = self._provider_manager.models.model_directory(model_id)
            presence[model_id] = all(
                (directory / asset.filename).is_file() for asset in model.files
            )
        self.structured.configure_provider(
            choice,
            file_presence=presence,
            locale="en-US" if locale == "All languages" else locale,
            job_speed=speed,
            suggestions=suggestions,
        )

    def _confirm_replace(self) -> bool:
        if not self.structured.dirty:
            return True
        answer = messagebox.askyesnocancel(
            APP_TITLE, "Save unsaved JSON changes before replacing or closing?"
        )
        if answer is None:
            return False
        if answer:
            return self._save_project_as()
        return True

    def _open_conversation(self) -> None:
        if self._busy or self._closing or not self._confirm_replace():
            return
        chosen = filedialog.askopenfilename(
            filetypes=[("JSON conversation", "*.json"), ("Plain text", "*.txt")]
        )
        if not chosen:
            return
        self._begin_work("import")
        self._status_var.set("Importing JSON...")
        revision = self._preview_revision
        token = self._cancellation_token
        self._worker = threading.Thread(
            target=self._run_import,
            args=(Path(chosen), revision, token),
            daemon=True,
        )
        self._worker.start()

    def _run_import(
        self,
        source: Path,
        revision: int,
        token: CancellationToken,
        kind: str = "document",
    ) -> None:
        try:
            token.raise_if_cancelled()
            if kind == "project":
                project = load_project(source)
                token.raise_if_cancelled()
                self._queue.put(
                    _ProgressMessage(
                        "project_ready", revision=revision, project=project
                    )
                )
                return
            if kind == "preset":
                preferences = preset_from_data(read_json_file(source))
                token.raise_if_cancelled()
                self._queue.put(
                    _ProgressMessage(
                        "preset_ready",
                        revision=revision,
                        preferences=tuple(preferences.items()),
                    )
                )
                return
            if source.suffix.lower() != ".json":
                if source.stat().st_size > 10 * 1024 * 1024:
                    raise ValueError("Text input exceeds the 10 MiB limit.")
                text = source.read_text(encoding="utf-8-sig")
                token.raise_if_cancelled()
                self._queue.put(
                    _ProgressMessage("text_ready", revision=revision, message=text)
                )
                return
            document = load_document(source)
            token.raise_if_cancelled()
            self._queue.put(
                _ProgressMessage(
                    "import_ready", revision=revision, document=document, path=source
                )
            )
        except asyncio.CancelledError:
            self._queue.put(_ProgressMessage("cancelled"))
        except (OSError, ValueError) as error:
            self._queue.put(_ProgressMessage("error", message=str(error)))

    def _save_json_as(self) -> bool:
        if self.structured.document is None:
            return False
        if self.structured.pending:
            messagebox.showerror(APP_TITLE, "Apply role/segment edits before saving.")
            return False
        chosen = filedialog.asksaveasfilename(
            title="Save JSON As (dialogue and source settings)",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not chosen:
            return False
        try:
            save_document_as(self.structured.document, Path(chosen))
        except OSError as error:
            messagebox.showerror(APP_TITLE, str(error))
            return False
        self._status_var.set(
            "JSON saved. Active voice assignments require a project save."
        )
        return True

    def _open_project(self) -> None:
        self._open_data_file("project", "*.ttsproject.json")

    def _apply_mapping_preset(self) -> None:
        if self.structured.document is None:
            return
        self._open_data_file("preset", "*.ttspreset.json")

    def _open_data_file(self, kind: str, pattern: str) -> None:
        if self._busy or self._closing:
            return
        if kind == "project" and not self._confirm_replace():
            return
        if self.structured.pending:
            messagebox.showerror(APP_TITLE, "Apply role/segment edits first.")
            return
        chosen = filedialog.askopenfilename(
            filetypes=[(kind, pattern), ("JSON", "*.json")]
        )
        if not chosen:
            return
        self._begin_work("import")
        self._worker = threading.Thread(
            target=self._run_import,
            args=(Path(chosen), self._preview_revision, self._cancellation_token, kind),
            daemon=True,
        )
        self._worker.start()

    def _capture_project(self) -> ProjectSnapshot:
        if self.structured.document is None or self.structured.pending:
            raise ValueError("Open a JSON document and apply pending edits first.")
        options = self._read_options()
        document = self.structured.document
        assignments = {
            provider: dict(voices)
            for provider, voices in self.structured.project_assignments.items()
        }
        for provider in self._choices:
            assignments.setdefault(provider, {}).update(
                self.structured.mappings.selections(document, provider)
            )
        assignments.setdefault(self._provider_id, {}).update(
            {
                item.speaker_id: item.voice_id
                for item in self.structured.preflight().assignments
            }
        )
        project = new_project(
            document,
            self._provider_id,
            assignments,
            export_settings=options.export_settings,
            text_settings=options.text_settings,
            speed=options.speed,
            locale=self._language_var.get(),
            source_locator=self._source_locator,
            source_sha256=self._source_sha256,
        )
        if self._project_id is not None:
            project = replace(project, project_id=self._project_id)
        return project

    def _save_project_as(self) -> bool:
        try:
            project = self._capture_project()
            chosen = filedialog.asksaveasfilename(
                title="Save project As",
                defaultextension=".ttsproject.json",
                filetypes=[("TTS project", "*.ttsproject.json")],
            )
            if not chosen:
                return False
            save_project(project, Path(chosen))
        except (OSError, ValueError) as error:
            messagebox.showerror(APP_TITLE, str(error))
            return False
        self._project_id = project.project_id
        self.structured.dirty = False
        self._status_var.set(
            "Project saved with embedded dialogue, mappings and settings."
        )
        return True

    def _adopt_project(self, project: ProjectSnapshot) -> None:
        self.structured.mappings = MappingState()
        self.structured.preferences = {}
        self.structured.set_document(project.document)
        self.structured.project_assignments = {
            provider: dict(voices) for provider, voices in project.assignments.items()
        }
        self._project_id = project.project_id
        self._source_locator = project.source_locator
        self._source_sha256 = project.source_sha256
        self._provider_var.set(self._choices[project.provider_id].display_name)
        self._provider_changed()
        self._language_var.set(project.locale)
        self._saved_chunk_limit = project.text_settings.max_chunk_characters
        self._saved_export_timeout = project.export_settings.timeout_seconds
        settings = project.export_settings
        self._format_var.set(settings.audio_format.upper())
        self._bitrate_var.set(
            str(settings.mp3_bitrate_kbps) if settings.mp3_bitrate_kbps else "Auto"
        )
        self._sample_rate_var.set(
            str(settings.sample_rate) if settings.sample_rate else "Native"
        )
        self._channels_var.set(
            {None: "Source", 1: "Mono", 2: "Stereo"}[settings.channels]
        )
        self._normalize_var.set(settings.normalize)
        self._speed_var.set(str(project.speed) if project.speed is not None else "1.0")
        self._sentence_pause_var.set(str(project.text_settings.sentence_pause_seconds))
        self._paragraph_pause_var.set(
            str(project.text_settings.paragraph_pause_seconds)
        )
        self._process_text_var.set(True)
        self._mode_tabs.select(self.structured)
        self._sync_structured_provider()
        self._apply_control_states()
        self.structured.dirty = False
        self._status_var.set(
            "Project restored from embedded snapshot; source locator is provenance only."
        )

    def _save_mapping_preset(self) -> None:
        if self.structured.document is None or self.structured.pending:
            return
        try:
            result = self.structured.preflight()
            voices = {item.speaker_id: item.voice_id for item in result.assignments}
            locale = self._language_var.get()
            if locale == "All languages":
                locale = "en-US"
            preferences = {
                (speaker.role.strip().casefold(), self._provider_id, locale): voices[
                    speaker.id
                ]
                for speaker in self.structured.document.speakers
            }
            chosen = filedialog.asksaveasfilename(
                title="Save mapping preset",
                defaultextension=".ttspreset.json",
                filetypes=[("Mapping preset", "*.ttspreset.json")],
            )
            if chosen:
                save_preset(preferences, Path(chosen))
        except (OSError, ValueError) as error:
            messagebox.showerror(APP_TITLE, str(error))

    def _generate_structured(self) -> None:
        if self._busy or self._closing:
            return
        try:
            if self.structured.pending:
                raise ValueError("Apply role/segment edits before generating.")
            options = self._read_options()
            self._sync_structured_provider()
            result = self.structured.preflight()
            if result.errors:
                raise ValueError(
                    "; ".join(f"{item.path}: {item.message}" for item in result.errors)
                )
            document = self.structured.document
            voices = {item.speaker_id: item.voice_id for item in result.assignments}
            final_audio = Path(self._output_path_var.get().strip())
            if final_audio.exists():
                if not messagebox.askyesno(
                    APP_TITLE, "Replace the existing output audio file?"
                ):
                    return
                options = replace(
                    options,
                    export_settings=replace(options.export_settings, overwrite=True),
                )
            validate_export_target(final_audio, options.export_settings)
        except (OSError, ValueError) as error:
            messagebox.showerror(APP_TITLE, str(error))
            return
        self._begin_work("generation")
        self._worker = threading.Thread(
            target=self._run_generation,
            args=(
                "",
                final_audio.parent / DEFAULT_OUTPUT_DIR.name,
                final_audio,
                voices,
                options,
                self._cancellation_token,
                document,
                self._preview_revision,
            ),
            daemon=True,
        )
        self._worker.start()

    def _preview_structured(self) -> None:
        if self._busy or self._closing:
            return
        try:
            if self.structured.pending:
                raise ValueError("Apply role/segment edits before preview.")
            self._sync_structured_provider()
            segment = self.structured.preview_segment()
            options = replace(self._read_voice_options(), speed=segment.speed)
        except ValueError as error:
            messagebox.showerror(APP_TITLE, str(error))
            return
        self._begin_work("preview")
        self._status_var.set("Preview: speech only; explicit after-pauses omitted.")
        self._worker = threading.Thread(
            target=self._run_preview,
            args=(
                options,
                segment.voice_id,
                segment.text,
                self._cancellation_token,
                self._preview_revision,
            ),
            daemon=True,
        )
        self._worker.start()

    def _on_generate_clicked(self) -> None:
        if "structured" in self.__dict__ and self._json_mode():
            self._generate_structured()
            return
        if self._closing or (self._worker is not None and self._worker.is_alive()):
            return
        script_text = self.text_box.get("1.0", "end")
        try:
            validate_script_text(script_text)
            voices = build_speaker_voice_mapping(
                [(speaker.get(), voice.get()) for speaker, voice in self._speaker_rows]
            )
            options = self._read_options()
        except ValueError as error:
            messagebox.showerror(APP_TITLE, str(error))
            return
        final_audio = Path(
            self._output_path_var.get().strip() or str(default_desktop_output_path())
        )
        if options.export_settings is not None:
            if final_audio.exists():
                if not messagebox.askyesno(
                    APP_TITLE, "Replace the existing output audio file?"
                ):
                    return
                options = replace(
                    options,
                    export_settings=replace(options.export_settings, overwrite=True),
                )
            try:
                validate_export_target(final_audio, options.export_settings)
            except (OSError, ValueError) as error:
                messagebox.showerror(APP_TITLE, str(error))
                return
        output_dir = final_audio.parent / DEFAULT_OUTPUT_DIR.name
        self._begin_work("generation")
        self._worker = threading.Thread(
            target=self._run_generation,
            args=(
                script_text,
                output_dir,
                final_audio,
                voices,
                options,
                self._cancellation_token,
            ),
            daemon=True,
        )
        self._worker.start()

    def _on_preview_clicked(self, slot: int) -> None:
        if "structured" in self.__dict__ and self._json_mode():
            self._preview_structured()
            return
        if self._closing or (self._worker is not None and self._worker.is_alive()):
            return
        try:
            options = self._read_voice_options()
            voice_id = self._speaker_rows[slot][1].get().strip()
            try:
                selected_text = self.text_box.get("sel.first", "sel.last")
            except tk.TclError:
                selected_text = None
            if selected_text:
                speakers = {
                    speaker.get().strip() for speaker, voice in self._speaker_rows
                }
                selected_text = strip_speaker_labels(selected_text, speakers)
        except ValueError as error:
            messagebox.showerror(APP_TITLE, str(error))
            return
        self._begin_work("preview")
        self._worker = threading.Thread(
            target=self._run_preview,
            args=(
                options,
                voice_id,
                selected_text,
                self._cancellation_token,
                self._preview_revision,
            ),
            daemon=True,
        )
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.generate_button.configure(
            state="disabled" if busy or self._closing else "normal"
        )
        self._cancel_button.configure(
            state="normal" if busy and not self._closing else "disabled"
        )
        self._apply_control_states()

    def _cancel_work(self) -> None:
        self._cancellation_token.cancel()
        self._status_var.set("Cancellation requested; waiting for cleanup...")

    def _invalidate_preview(self) -> None:
        self._preview_revision += 1
        self._last_preview = None
        self._player.stop()
        if self._operation_kind == "preview" and self._busy:
            self._cancellation_token.cancel()
        self._replay_button.configure(state="disabled")

    def _stop_playback(self) -> None:
        self._player.stop()

    def _replay_preview(self) -> None:
        if self._last_preview is not None:
            try:
                self._player.play(self._last_preview)
            except (OSError, RuntimeError) as error:
                messagebox.showerror(APP_TITLE, f"Could not play the preview: {error}")

    def _run_generation(
        self,
        script_text: str,
        output_dir: Path,
        final_audio: Path,
        voices: dict[str, str],
        options: DesktopGenerationOptions,
        token: CancellationToken,
        document: ConversationDocument | None = None,
        revision: int = 0,
    ) -> None:
        def on_progress(index: int, total: int, line: ConversationLine) -> None:
            self._queue.put(
                _ProgressMessage(
                    "progress", index=index, total=total, speaker=line.speaker
                )
            )

        def on_chunk_progress(index: int, total: int, chunk: SpeechChunk) -> None:
            self._queue.put(
                _ProgressMessage(
                    "chunk_progress", index=index, total=total, speaker=chunk.speaker
                )
            )

        def on_export_progress(stage: str) -> None:
            self._queue.put(_ProgressMessage("export_progress", message=stage))

        try:
            provider = self._provider_manager.get(options.provider_id)
            result = asyncio.run(
                generate_conversation(
                    input_text=script_text if document is None else None,
                    document=document,
                    voice_assignments=voices if document is not None else None,
                    output_dir=output_dir,
                    final_audio=final_audio,
                    voices=voices,
                    on_progress=on_progress,
                    on_chunk_progress=on_chunk_progress,
                    provider_id=options.provider_id,
                    provider=provider,
                    cancellation_token=token,
                    speed=options.speed,
                    text_settings=options.text_settings,
                    export_settings=options.export_settings,
                    on_export_progress=on_export_progress,
                )
            )
            self._queue.put(
                _ProgressMessage(
                    "success", final_audio=result, revision=revision, document=document
                )
            )
        except asyncio.CancelledError:
            self._queue.put(_ProgressMessage("cancelled"))
        except Exception as error:
            self._queue.put(
                _ProgressMessage("error", message=format_generation_error(error))
            )

    def _run_preview(
        self,
        options: DesktopGenerationOptions,
        voice_id: str,
        selected_text: str | None,
        token: CancellationToken,
        revision: int,
    ) -> None:
        try:
            output = asyncio.run(
                self._preview_service.generate(
                    options.provider_id, voice_id, selected_text, options.speed, token
                )
            )
            self._queue.put(
                _ProgressMessage("preview_ready", path=output, revision=revision)
            )
        except asyncio.CancelledError:
            self._queue.put(_ProgressMessage("cancelled"))
        except Exception as error:
            self._queue.put(
                _ProgressMessage("error", message=format_generation_error(error))
            )

    def _drain_queue(self) -> None:
        try:
            while True:
                self._handle_message(self._queue.get_nowait())
        except queue.Empty:
            pass
        if self._busy and not self._closing:
            self._elapsed_var.set(
                f"Elapsed: {time.monotonic() - self._started_at:.1f} s"
            )
        if self._closing and (self._worker is None or not self._worker.is_alive()):
            if not self._shutdown_started:
                self._shutdown_started = True
                self._worker = threading.Thread(
                    target=self._provider_manager.close, daemon=True
                )
                self._worker.start()
            else:
                self.destroy()
                return
        self.after(self.POLL_INTERVAL_MS, self._drain_queue)

    def _handle_message(self, message: _ProgressMessage) -> None:
        if message.kind in {
            "import_ready",
            "text_ready",
            "project_ready",
            "preset_ready",
        }:
            self._set_busy(False)
            if (
                self._closing
                or message.revision != self._preview_revision
                or self._cancellation_token.is_cancelled
            ):
                self._status_var.set(
                    "Import discarded because the active revision changed."
                )
                return
            if message.kind == "project_ready":
                self._adopt_project(message.project)
                return
            if message.kind == "preset_ready":
                self.structured.preferences = dict(message.preferences)
                self.structured.dirty = True
                self.structured.refresh()
                self._invalidate_preview()
                self._status_var.set(
                    "Preset enabled for automatic roles; manual/project choices retained."
                )
                return
            if message.kind == "text_ready":
                self.text_box.delete("1.0", "end")
                self.text_box.insert("1.0", message.message)
                self._mode_tabs.select(0)
                self._status_var.set("Plain text imported.")
                return
            self.structured.set_document(message.document)
            self._project_id = None
            self._saved_chunk_limit = 1000
            self._saved_export_timeout = 600.0
            self._source_locator = str(message.path) if message.path else None
            self._source_sha256 = message.document.content_hash
            self._mode_tabs.select(self.structured)
            self._status_var.set(
                "JSON imported. Directions are notes; preview is speech only."
            )
            return
        if message.kind == "export_progress":
            if not self._exporting:
                self.progress_bar.configure(mode="indeterminate")
                self.progress_bar.start(10)
                self._exporting = True
            self._status_var.set(message.message)
            return
        if message.kind in {"progress", "chunk_progress"}:
            if message.kind == "chunk_progress":
                self._chunk_progress_active = True
            if message.kind == "chunk_progress" or not self._chunk_progress_active:
                self.progress_bar.configure(value=message.index, maximum=message.total)
            self._status_var.set(
                f"Generating {message.speaker}: {message.index}/{message.total}..."
            )
            return
        if self._exporting:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self._exporting = False
        self._set_busy(False)
        if self._closing:
            return
        if message.kind == "success":
            if (
                message.document is not None
                and message.revision != self._preview_revision
            ):
                self._status_var.set(
                    "Snapshot exported; current document has newer edits."
                )
                return
            final_audio = message.final_audio
            self._status_var.set(f"Done. Saved to: {final_audio}")
            messagebox.showinfo(APP_TITLE, f"Final audio created:\n{final_audio}")
        elif message.kind == "preview_ready":
            if (
                message.revision != self._preview_revision
                or self._cancellation_token.is_cancelled
            ):
                self._status_var.set(
                    "Preview settings changed; generate a new preview."
                )
                return
            self._last_preview = message.path
            self._replay_button.configure(state="normal")
            self._status_var.set("Preview ready. Play/replay or stop at any time.")
            self._replay_preview()
        elif message.kind == "cancelled":
            self._status_var.set("Cancelled. Existing final audio is preserved.")
        elif message.kind == "error":
            self._status_var.set("Operation failed. See the error message.")
            messagebox.showerror(APP_TITLE, message.message)

    def _on_close(self) -> None:
        if "structured" in self.__dict__ and not self._confirm_replace():
            return
        self._closing = True
        self._set_busy(True)
        self._cancellation_token.cancel()
        self._player.stop()
        self._status_var.set("Waiting for cleanup before closing...")


def main() -> None:
    app = TTSDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
