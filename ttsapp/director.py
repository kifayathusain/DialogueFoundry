"""Immutable Audio Director plans, scoped discovery and manual editing.

This module performs no synthesis and imports no widgets. File IDs are relative
source names, never paths supplied by a planner. Source snapshots retain the
difference between omitted and explicit zero pauses.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .audio_effects import AudioTreatment
from .audio_export import ExportSettings, validate_export_target
from .conversation_document import (
    MAX_INPUT_BYTES,
    ConversationDocument,
    parse_document_text,
)
from .provider_manager import ProviderChoice
from .providers.base import CancellationToken
from .speaker_mapping import resolve_document

MAX_BATCH_FILES = 200
MAX_BATCH_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class SourceFile:
    """A validated source snapshot or an actionable invalid candidate."""

    file_id: str
    path: Path
    fingerprint: str
    document: ConversationDocument | None
    error: str = ""


@dataclass(frozen=True)
class ScanResult:
    """Stable discovery results; unrelated JSON is explicitly excluded."""

    files: tuple[SourceFile, ...]
    excluded: tuple[str, ...]


@dataclass(frozen=True)
class TimingSettings:
    """Bounds for automatic gaps, used only at omitted nonfinal boundaries."""

    mode: str = "script"
    minimum: float = 0.12
    maximum: float = 0.45

    def __post_init__(self) -> None:
        if self.mode not in {"script", "natural"}:
            raise ValueError(
                "Timing must be script or natural; overlap is unsupported."
            )
        _number(self.minimum, 0, 2, "Minimum gap")
        _number(self.maximum, self.minimum, 2, "Maximum gap")


def _number(value: float, low: float, high: float, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"{label} must be a finite number between {low} and {high}.")


@dataclass(frozen=True)
class PhoneScope:
    """One speaker's inclusive one-based segment range heard over a phone."""

    speaker: str
    start: int
    end: int


@dataclass(frozen=True)
class IncidentalCue:
    """An approved locally generated noise at the start of one speech turn."""

    segment: int
    kind: str


@dataclass(frozen=True)
class SceneSettings:
    """Acoustics independent from conversational timing; silence stays untouched."""

    phone: tuple[PhoneScope, ...] = ()
    room_level: float = 0
    cues: tuple[IncidentalCue, ...] = ()

    def __post_init__(self) -> None:
        _number(self.room_level, 0, 0.015, "Room level")
        if any(cue.kind not in {"paper", "chair"} for cue in self.cues):
            raise ValueError("Supported incidental cues are paper and chair only.")
        if len({cue.segment for cue in self.cues}) != len(self.cues):
            raise ValueError("Choose at most one incidental cue per turn.")


@dataclass(frozen=True)
class FilePlan:
    """Reviewed immutable settings for exactly one input conversation."""

    source: SourceFile
    provider_id: str
    cast: tuple[tuple[str, str], ...]
    destination_name: str
    speed: float | None = None
    timing: TimingSettings = TimingSettings()
    scene: SceneSettings = SceneSettings()
    overwrite: bool = False
    skipped: bool = False
    manual_fields: frozenset[str] = frozenset()
    issues: tuple[str, ...] = ()
    resolved_after_pauses: tuple[float, ...] = field(init=False)

    def __post_init__(self) -> None:
        pauses = []
        if self.source.document is not None:
            segments = self.source.document.to_dict()["segments"]
            for index, segment in enumerate(segments):
                pause = segment.get("pause_after_seconds", 0)
                if (
                    self.timing.mode == "natural"
                    and "pause_after_seconds" not in segment
                    and index + 1 < len(segments)
                    and segment["speaker"] != segments[index + 1]["speaker"]
                ):
                    following = segments[index + 1]
                    pause = (self.timing.minimum + self.timing.maximum) / 2
                    if len(following["text"].split()) <= 4:
                        pause = self.timing.minimum
                    elif segment["text"].rstrip().endswith("?"):
                        pause = self.timing.maximum
                    pause = round(pause, 4)
                pauses.append(pause)
        object.__setattr__(self, "resolved_after_pauses", tuple(pauses))


@dataclass(frozen=True)
class BatchPlan:
    """Versioned run snapshot shared by manual, preset and AI workflows."""

    input_folder: Path
    output_folder: Path
    files: tuple[FilePlan, ...]
    audio_format: str = "mp3"
    failure_policy: str = "continue"
    offline: bool = True
    revision: int = 0
    schema_version: int = 1

    def __post_init__(self) -> None:
        ExportSettings(audio_format=self.audio_format)
        if self.schema_version != 1:
            raise ValueError("Unsupported Audio Director plan version.")
        if self.failure_policy not in {"continue", "stop"}:
            raise ValueError("Failure policy must be continue or stop.")
        ids = [item.source.file_id for item in self.files]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate file IDs in batch.")


def fingerprint(data: bytes) -> str:
    """Hash source bytes without recording their private contents."""
    return hashlib.sha256(data).hexdigest()


def scan_folder(
    folder: Path, recursive: bool = False, token: CancellationToken | None = None
) -> ScanResult:
    """Discover bounded conversation candidates without following external links."""
    token = token or CancellationToken()
    folder = folder.resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("Select an input folder.")
    paths = folder.rglob("*") if recursive else folder.iterdir()
    selected = []
    for path in paths:
        token.raise_if_cancelled()
        if path.is_file() and path.suffix.lower() == ".json":
            selected.append(path)
            if len(selected) > MAX_BATCH_FILES:
                raise ValueError(
                    f"Select at most {MAX_BATCH_FILES} JSON files per batch."
                )
    files = []
    excluded = []
    total_bytes = 0
    for path in sorted(selected, key=lambda item: (str(item).casefold(), str(item))):
        token.raise_if_cancelled()
        file_id = path.relative_to(folder).as_posix()
        if not path.resolve().is_relative_to(folder):
            excluded.append(f"{file_id}: link outside input folder")
            continue
        try:
            with path.open("rb") as stream:
                data = stream.read(MAX_INPUT_BYTES + 1)
            total_bytes += len(data)
            if total_bytes > MAX_BATCH_BYTES:
                raise OSError("Select a smaller batch: source data exceeds 64 MiB.")
            text = data.decode("utf-8-sig")
            try:
                root = json.loads(text)
            except (ValueError, RecursionError):
                root = None
            if isinstance(root, dict):
                candidate = "speakers" in root or "segments" in root
            else:
                candidate = bool(re.search(r'"(?:speakers|segments)"\s*:', text))
            if not candidate:
                excluded.append(f"{file_id}: not a conversation document")
                continue
            document = parse_document_text(data)
            files.append(SourceFile(file_id, path, fingerprint(data), document))
        except (OSError, UnicodeError, ValueError, RecursionError) as error:
            files.append(SourceFile(file_id, path, "", None, str(error)))
    if total_bytes > MAX_BATCH_BYTES:
        raise ValueError("Select a smaller batch: source data exceeds 64 MiB.")
    return ScanResult(tuple(files), tuple(excluded))


def manual_plan(
    scan: ScanResult,
    input_folder: Path,
    output_folder: Path,
    choice: ProviderChoice,
    *,
    audio_format: str = "mp3",
    offline: bool = True,
) -> BatchPlan:
    """Resolve independent casts without linking equal display-role names."""
    files = []
    used_voices: set[str] = set()
    for source in scan.files:
        cast = ()
        if source.document is not None:
            independent_choice = replace(
                choice,
                voices=tuple(
                    sorted(
                        choice.voices, key=lambda voice: voice.voice_id in used_voices
                    )
                ),
            )
            resolved = resolve_document(
                source.document, independent_choice, locale="en-GB"
            )
            cast = tuple(
                (item.speaker_id, item.voice_id) for item in resolved.assignments
            )
            used_voices.update(voice for _, voice in cast)
        files.append(
            FilePlan(
                source, choice.provider_id, cast, f"{source.path.stem}.{audio_format}"
            )
        )
    return BatchPlan(
        input_folder.resolve(),
        output_folder.resolve(),
        tuple(files),
        audio_format,
        offline=offline,
    )


def edit_file(plan: BatchPlan, file_id: str, **changes: object) -> BatchPlan:
    """Retain explicit corrections across subsequent AI replans."""
    editable = {
        "provider_id",
        "cast",
        "destination_name",
        "speed",
        "timing",
        "scene",
        "overwrite",
        "skipped",
        "issues",
    }
    if not changes.keys() <= editable:
        raise ValueError("Unknown plan setting.")
    if file_id not in {item.source.file_id for item in plan.files}:
        raise ValueError("Unknown file ID.")
    files = tuple(
        replace(item, **changes, manual_fields=item.manual_fields | changes.keys())
        if item.source.file_id == file_id
        else item
        for item in plan.files
    )
    return replace(plan, files=files, revision=plan.revision + 1)


def bind_cast(
    plan: BatchPlan, members: tuple[tuple[str, str], ...], voice_id: str
) -> BatchPlan:
    """Explicitly link selected recurring identities, never equal display names."""
    provider_ids = {
        item.provider_id
        for item in plan.files
        if any(file_id == item.source.file_id for file_id, _ in members)
    }
    if len(provider_ids) != 1:
        raise ValueError("A linked cast must use a single provider.")
    for file_id, speaker in members:
        item = next(
            (item for item in plan.files if item.source.file_id == file_id), None
        )
        if item is None or speaker not in dict(item.cast):
            raise ValueError("Unknown cast member.")
        cast = dict(item.cast)
        cast[speaker] = voice_id
        plan = edit_file(plan, file_id, cast=tuple(cast.items()))
    return plan


def resolved_document(item: FilePlan) -> ConversationDocument:
    """Freeze eligible context-sensitive gaps while preserving every source word."""
    document = item.source.document
    if document is None:
        raise ValueError(item.source.error or "Invalid conversation document.")
    data = document.to_dict()
    segments = data["segments"]
    for segment, pause in zip(segments, item.resolved_after_pauses, strict=True):
        segment["pause_after_seconds"] = pause
    return document.with_data(data)


def treatments(item: FilePlan) -> dict[int, AudioTreatment]:
    """Resolve fixed effects per speech segment before any audio is generated."""
    document = item.source.document
    if document is None:
        return {}
    cues = {cue.segment: cue.kind for cue in item.scene.cues}
    return {
        index: AudioTreatment(
            telephone=any(
                scope.speaker == segment.speaker and scope.start <= index <= scope.end
                for scope in item.scene.phone
            ),
            room_level=item.scene.room_level,
            cue=cues.get(index),
        )
        for index, segment in enumerate(document.segments, 1)
    }


def validate_name(name: str, audio_format: str) -> None:
    """Allow a Windows filename only, never a planner-controlled path."""
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(
        f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
    )
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 180
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
        or name.endswith((" ", "."))
        or name.split(".")[0].upper() in reserved
        or Path(name).suffix.lower() != f".{audio_format}"
    ):
        raise ValueError(
            "Choose a plain Windows filename with the selected audio extension."
        )


def preflight(
    plan: BatchPlan, choices: tuple[ProviderChoice, ...], *, check_sources: bool = False
) -> dict[str, tuple[str, ...]]:
    """Validate a whole batch before synthesis, including all destination collisions."""
    providers = {choice.provider_id: choice for choice in choices}
    counts = Counter(
        item.destination_name.casefold() for item in plan.files if not item.skipped
    )
    errors = {}
    for item in plan.files:
        messages = list(item.issues)
        if item.skipped:
            errors[item.source.file_id] = ()
            continue
        try:
            if item.source.error:
                raise ValueError(item.source.error)
            validate_name(item.destination_name, plan.audio_format)
            if counts[item.destination_name.casefold()] > 1:
                raise ValueError("Duplicate destination; rename or skip a file.")
            if not item.source.path.resolve().is_relative_to(
                plan.input_folder.resolve()
            ):
                raise ValueError("Source is outside the selected input folder.")
            if (
                plan.output_folder.resolve() == plan.input_folder.resolve()
                and item.destination_name.lower().endswith(".json")
            ):
                raise ValueError("Outputs must not replace sources.")
            choice = providers.get(item.provider_id)
            if choice is None:
                raise ValueError("Select an available provider.")
            if plan.offline and choice.online:
                raise ValueError("Fully offline mode requires a local TTS provider.")
            document = resolved_document(item)
            if len(dict(item.cast)) != len(item.cast):
                raise ValueError("Duplicate cast speaker IDs.")
            if set(dict(item.cast)) != {speaker.id for speaker in document.speakers}:
                raise ValueError("Cast must include exactly the declared speaker IDs.")
            resolved = resolve_document(
                document, choice, current=dict(item.cast), job_speed=item.speed
            )
            messages.extend(diagnostic.message for diagnostic in resolved.errors)
            for scope in item.scene.phone:
                if (
                    scope.speaker not in dict(item.cast)
                    or type(scope.start) is not int
                    or type(scope.end) is not int
                    or not 1 <= scope.start <= scope.end <= len(document.segments)
                ):
                    raise ValueError(
                        "Phone scope needs a known speaker and valid segment range."
                    )
            for cue in item.scene.cues:
                if type(cue.segment) is not int or not 1 <= cue.segment <= len(
                    document.segments
                ):
                    raise ValueError("Incidental cue has an invalid segment index.")
            if len(item.scene.cues) > max(1, len(document.segments) // 3):
                raise ValueError(
                    "Use sparse incidental cues: at most one per three turns."
                )
            if check_sources:
                with item.source.path.open("rb") as stream:
                    current = stream.read(MAX_INPUT_BYTES + 1)
                if fingerprint(current) != item.source.fingerprint:
                    raise ValueError(
                        "Source changed after review; rescan and review this file."
                    )
            validate_export_target(
                plan.output_folder / item.destination_name,
                ExportSettings(
                    audio_format=plan.audio_format, overwrite=item.overwrite
                ),
            )
        except (OSError, ValueError) as error:
            messages.append(str(error))
        errors[item.source.file_id] = tuple(messages)
    return errors


def plan_settings(item: FilePlan) -> dict[str, object]:
    """Return safe reusable settings without source text, prompts or credentials."""
    return {
        "provider": item.provider_id,
        "voices": dict(item.cast),
        "speed": item.speed,
        "timing": asdict(item.timing),
        "scene": {
            "phone": [asdict(scope) for scope in item.scene.phone],
            "room_level": item.scene.room_level,
            "cues": [asdict(cue) for cue in item.scene.cues],
        },
    }
