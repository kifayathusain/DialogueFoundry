"""Versioned conversation JSON, independent of widgets, providers and synthesis."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_SEGMENTS = 10_000
MAX_SPEAKERS = 1_000
MAX_PAUSE_SECONDS = 600
MAX_TOTAL_PAUSE_SECONDS = 86_400
MIN_SPEED = 0.5
MAX_SPEED = 2.0
MAX_CONTAINER_DEPTH = 64
MAX_DIAGNOSTICS = 100


@dataclass(frozen=True)
class DocumentDiagnostic:
    """A stable code and semantic path; syntax errors also locate line/column."""

    code: str
    path: str
    message: str
    severity: Literal["error", "warning"] = "error"
    line: int | None = None
    column: int | None = None


class DocumentValidationError(ValueError):
    """Invalid input with bounded, actionable diagnostics and no dialogue dump."""

    def __init__(self, diagnostics: tuple[DocumentDiagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        super().__init__(
            "; ".join(f"{item.path}: {item.message}" for item in diagnostics)
        )


class DocumentIOError(OSError):
    """A conversation file could not be read or atomically saved."""


@dataclass(frozen=True)
class SpeechSettings:
    """Explicit structured speed, unset when omitted; no provider interpretation."""

    speed: int | float | None = None


@dataclass(frozen=True)
class DocumentSpeaker:
    """Case-sensitive identity and display/voice notes for a declared role."""

    id: str
    role: str
    voice_direction: str = ""
    voice_defaults: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )
    speech: SpeechSettings = field(default_factory=SpeechSettings)


@dataclass(frozen=True)
class DocumentSegment:
    """Original dialogue and timing for one ordered segment."""

    speaker: str
    text: str
    pause_after_seconds: int | float = 0
    voice_direction: str = ""
    speech: SpeechSettings = field(default_factory=SpeechSettings)


@dataclass(frozen=True)
class ConversationDocument:
    """Immutable worker snapshot with a separate active identity and revision.

    The private JSON snapshot preserves optional-field absence and extensions.
    ``to_dict`` returns a fresh tree, so callers cannot mutate saved state.
    """

    schema_version: int
    speakers: tuple[DocumentSpeaker, ...]
    segments: tuple[DocumentSegment, ...]
    diagnostics: tuple[DocumentDiagnostic, ...]
    document_id: str
    revision: int
    content_hash: str
    _source_json: str = field(repr=False)

    def to_dict(self) -> dict[str, object]:
        """Return an isolated copy of all known and extension source fields."""
        return json.loads(self._source_json)

    def with_data(self, data: object) -> ConversationDocument:
        """Validate an edit and advance revision while retaining active identity."""
        return parse_document_data(data, reload_of=self)


class _Diagnostics:
    def __init__(self) -> None:
        self.errors: list[DocumentDiagnostic] = []
        self.warnings: list[DocumentDiagnostic] = []

    def add(self, code: str, path: str, message: str, *, warning: bool = False) -> None:
        items = self.warnings if warning else self.errors
        severity = "warning" if warning else "error"
        if len(items) < MAX_DIAGNOSTICS:
            items.append(DocumentDiagnostic(code, path, message, severity))
        elif len(items) == MAX_DIAGNOSTICS:
            items.append(
                DocumentDiagnostic(
                    "diagnostics_omitted",
                    "$",
                    "Additional diagnostics omitted.",
                    severity,
                )
            )

    def raise_errors(self) -> None:
        if self.errors:
            raise DocumentValidationError(tuple(self.errors))


def _invalid(code: str, message: str) -> DocumentValidationError:
    return DocumentValidationError((DocumentDiagnostic(code, "$", message),))


def _child(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key, ensure_ascii=True)}]"


def _check_text_depth(text: str, limit: int = MAX_CONTAINER_DEPTH) -> None:
    """Scan JSON containers before decoding; braces in strings are not nesting."""
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > limit:
                raise _invalid("depth_limit", f"JSON container depth exceeds {limit}.")
        elif character in "]}":
            depth -= 1


class _ObjectPairs(list):
    """Distinguish object pairs from arrays until duplicate keys are checked."""


def _convert_json(value: object, path: str, issues: _Diagnostics) -> object:
    if isinstance(value, _ObjectPairs):
        result: dict[str, object] = {}
        for key, child in value:
            child_path = _child(path, key)
            _convert_json(key, child_path, issues)
            if key in result:
                issues.add("duplicate_key", child_path, "Duplicate object key.")
            result[key] = _convert_json(child, child_path, issues)
        return result
    if isinstance(value, list):
        return [
            _convert_json(child, f"{path}[{index}]", issues)
            for index, child in enumerate(value)
        ]
    if isinstance(value, float) and not math.isfinite(value):
        issues.add("non_finite_number", path, "Numbers must be finite.")
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            issues.add("invalid_unicode", path, "Text must contain valid Unicode.")
    return value


def _check_data_depth(data: object) -> None:
    """Bound Python trees (including cycles) before recursive JSON encoding."""
    stack = [(data, 0)]
    while stack:
        value, parent_depth = stack.pop()
        if isinstance(value, (dict, list)):
            depth = parent_depth + 1
            if depth > MAX_CONTAINER_DEPTH:
                raise _invalid("depth_limit", "JSON container depth exceeds 64.")
            children = value.values() if isinstance(value, dict) else value
            if isinstance(value, dict) and any(not isinstance(k, str) for k in value):
                raise _invalid("invalid_type", "JSON object keys must be strings.")
            stack.extend((child, depth) for child in children)
        elif value is not None and type(value) not in (str, int, float, bool):
            raise _invalid("invalid_type", "Input must contain only JSON values.")


def parse_document_data(
    data: object, *, reload_of: ConversationDocument | None = None
) -> ConversationDocument:
    """Parse a Python JSON tree with the same validation and byte/depth limits.

    Byte size is measured as compact, unescaped UTF-8 JSON for Python trees.
    New imports get new identities. Only explicit reloads/edits retain identity.
    """
    _check_data_depth(data)
    pieces: list[str] = []
    size = 0
    try:
        for piece in json.JSONEncoder(
            ensure_ascii=False, separators=(",", ":")
        ).iterencode(data):
            size += len(piece.encode("utf-8"))
            if size > MAX_INPUT_BYTES:
                raise _invalid("size_limit", "JSON input exceeds 10 MiB.")
            pieces.append(piece)
    except (UnicodeEncodeError, ValueError) as error:
        if isinstance(error, DocumentValidationError):
            raise
        raise _invalid(
            "invalid_json", "Input cannot be encoded as UTF-8 JSON."
        ) from error
    return parse_document_text("".join(pieces), reload_of=reload_of)


def parse_document_text(
    source: str | bytes, *, reload_of: ConversationDocument | None = None
) -> ConversationDocument:
    """Parse UTF-8 JSON (with optional BOM) without inference or network access."""
    data, issues, text = _decode_json(source, MAX_INPUT_BYTES)
    return _validate_document(data, issues, reload_of, text)


def decode_json_value(
    source: str | bytes,
    *,
    max_bytes: int = MAX_INPUT_BYTES,
    max_depth: int = MAX_CONTAINER_DEPTH,
) -> object:
    """Decode bounded data-only JSON with duplicate/depth/nonfinite protection."""
    data, issues, _ = _decode_json(source, max_bytes, max_depth)
    issues.raise_errors()
    return data


def _decode_json(
    source: str | bytes,
    max_bytes: int,
    max_depth: int = MAX_CONTAINER_DEPTH,
) -> tuple[object, _Diagnostics, str]:
    try:
        raw = source.encode("utf-8") if isinstance(source, str) else source
        if len(raw) > max_bytes:
            raise _invalid(
                "size_limit", f"JSON input exceeds {max_bytes // (1024 * 1024)} MiB."
            )
        text = raw.decode("utf-8-sig")
    except UnicodeError as error:
        raise _invalid("invalid_encoding", "Input must be valid UTF-8.") from error
    _check_text_depth(text, max_depth)
    try:
        pairs = json.loads(text, object_pairs_hook=_ObjectPairs)
    except json.JSONDecodeError as error:
        diagnostic = DocumentDiagnostic(
            "json_syntax",
            "$",
            "Malformed JSON.",
            line=error.lineno,
            column=error.colno,
        )
        raise DocumentValidationError((diagnostic,)) from error
    except ValueError as error:
        raise _invalid("invalid_number", "JSON number cannot be decoded.") from error
    issues = _Diagnostics()
    data = _convert_json(pairs, "$", issues)
    return data, issues, text


def load_document(
    path: Path, *, reload_of: ConversationDocument | None = None
) -> ConversationDocument:
    """Read a bounded UTF-8 file; never save implicitly back to this source."""
    try:
        with path.open("rb") as source:
            if os.fstat(source.fileno()).st_size > MAX_INPUT_BYTES:
                raise _invalid("size_limit", "JSON input exceeds 10 MiB.")
            raw = source.read(MAX_INPUT_BYTES + 1)
    except OSError as error:
        raise DocumentIOError("Unable to read the conversation file.") from error
    return parse_document_text(raw, reload_of=reload_of)


def _object(value: object, path: str, issues: _Diagnostics) -> dict[str, object]:
    if not isinstance(value, dict):
        issues.add("invalid_type", path, "Expected an object.")
        return {}
    return value


def _extensions(
    data: dict[str, object], known: set[str], path: str, issues: _Diagnostics
) -> None:
    for key in data:
        if key not in known:
            issues.add(
                "unknown_field",
                _child(path, key),
                "Unknown extension field preserved.",
                warning=True,
            )


def _string(
    data: dict[str, object],
    key: str,
    path: str,
    issues: _Diagnostics,
    *,
    required: bool = True,
    identifier: bool = False,
) -> str:
    location = _child(path, key)
    if key not in data:
        if required:
            issues.add("missing_field", location, "Required field is missing.")
        return ""
    value = data[key]
    if not isinstance(value, str):
        issues.add("invalid_type", location, "Expected a string.")
        return ""
    if required and not value.strip():
        issues.add("empty_string", location, "Value must not be blank.")
    if identifier and value != value.strip():
        issues.add("invalid_id", location, "IDs must not have surrounding whitespace.")
    return value


def _number(
    value: object, path: str, minimum: float, maximum: float, issues: _Diagnostics
) -> int | float | None:
    if type(value) not in (int, float):
        issues.add("invalid_type", path, "Expected a number, excluding booleans.")
    elif isinstance(value, float) and not math.isfinite(value):
        # The recursive JSON conversion already reports this at the exact path.
        return None
    elif not minimum <= value <= maximum:
        issues.add(
            "number_range", path, f"Number must be between {minimum} and {maximum}."
        )
    else:
        return value
    return None


def _speech(data: dict[str, object], path: str, issues: _Diagnostics) -> SpeechSettings:
    if "speech" not in data:
        return SpeechSettings()
    location = _child(path, "speech")
    settings = _object(data["speech"], location, issues)
    _extensions(settings, {"speed"}, location, issues)
    speed = None
    if "speed" in settings:
        speed = _number(
            settings["speed"], f"{location}.speed", MIN_SPEED, MAX_SPEED, issues
        )
    return SpeechSettings(speed)


def _array(
    data: dict[str, object], key: str, limit: int, issues: _Diagnostics
) -> list[object]:
    path = f"$.{key}"
    if key not in data:
        issues.add("missing_field", path, "Required array is missing.")
        return []
    value = data[key]
    if not isinstance(value, list):
        issues.add("invalid_type", path, "Expected an array.")
        return []
    if not value or len(value) > limit:
        issues.add("count_limit", path, f"Array must contain 1 to {limit} items.")
        return []
    return value


def _speaker(value: object, path: str, issues: _Diagnostics) -> DocumentSpeaker:
    data = _object(value, path, issues)
    _extensions(
        data,
        {"id", "role", "voice_direction", "voice_defaults", "speech"},
        path,
        issues,
    )
    identifier = _string(data, "id", path, issues, identifier=True)
    role = _string(data, "role", path, issues)
    direction = _string(data, "voice_direction", path, issues, required=False)
    defaults: dict[str, str] = {}
    if "voice_defaults" in data:
        location = f"{path}.voice_defaults"
        entries = _object(data["voice_defaults"], location, issues)
        for key in entries:
            if not key.strip() or key != key.strip():
                issues.add(
                    "invalid_id",
                    _child(location, key),
                    "Provider IDs must be nonblank and trimmed.",
                )
            defaults[key] = _string(entries, key, location, issues, identifier=True)
    return DocumentSpeaker(
        identifier,
        role,
        direction,
        MappingProxyType(defaults),
        _speech(data, path, issues),
    )


def _segment(value: object, path: str, issues: _Diagnostics) -> DocumentSegment:
    data = _object(value, path, issues)
    _extensions(
        data,
        {"speaker", "text", "pause_after_seconds", "voice_direction", "speech"},
        path,
        issues,
    )
    speaker = _string(data, "speaker", path, issues, identifier=True)
    text = _string(data, "text", path, issues)
    direction = _string(data, "voice_direction", path, issues, required=False)
    pause = 0
    if "pause_after_seconds" in data:
        pause = _number(
            data["pause_after_seconds"],
            f"{path}.pause_after_seconds",
            0,
            MAX_PAUSE_SECONDS,
            issues,
        )
    return DocumentSegment(
        speaker, text, pause or 0, direction, _speech(data, path, issues)
    )


def _validate_document(
    value: object,
    issues: _Diagnostics,
    reload_of: ConversationDocument | None,
    source_json: str,
) -> ConversationDocument:
    data = _object(value, "$", issues)
    _extensions(data, {"schema_version", "speakers", "segments"}, "$", issues)
    version = data.get("schema_version", 1)
    if type(version) is not int:
        issues.add(
            "invalid_type", "$.schema_version", "Schema version must be integer 1."
        )
    elif version != 1:
        issues.add(
            "unsupported_version",
            "$.schema_version",
            "Only schema version 1 is supported.",
        )
    speakers = tuple(
        _speaker(item, f"$.speakers[{index}]", issues)
        for index, item in enumerate(_array(data, "speakers", MAX_SPEAKERS, issues))
    )
    segments = tuple(
        _segment(item, f"$.segments[{index}]", issues)
        for index, item in enumerate(_array(data, "segments", MAX_SEGMENTS, issues))
    )
    ids: set[str] = set()
    for index, speaker in enumerate(speakers):
        if speaker.id in ids:
            issues.add(
                "duplicate_id", f"$.speakers[{index}].id", "Speaker ID must be unique."
            )
        ids.add(speaker.id)
    for index, segment in enumerate(segments):
        if segment.speaker and segment.speaker not in ids:
            issues.add(
                "unknown_speaker",
                f"$.segments[{index}].speaker",
                "Reference must match a declared speaker ID.",
            )
    if (
        sum(segment.pause_after_seconds for segment in segments)
        > MAX_TOTAL_PAUSE_SECONDS
    ):
        issues.add(
            "total_pause_limit",
            "$.segments",
            "Total explicit silence exceeds 86400 seconds.",
        )
    issues.raise_errors()
    used = {segment.speaker for segment in segments}
    for index, speaker in enumerate(speakers):
        if speaker.id not in used:
            issues.add(
                "unused_speaker",
                f"$.speakers[{index}].id",
                "Declared speaker is unused.",
                warning=True,
            )
    canonical = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    document = ConversationDocument(
        1,
        speakers,
        segments,
        tuple(issues.warnings),
        str(uuid4()),
        0,
        hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        source_json,
    )
    if reload_of is not None:
        document = replace(
            document, document_id=reload_of.document_id, revision=reload_of.revision + 1
        )
    return document


def serialize_document(document: ConversationDocument) -> str:
    """Serialize source values/ordering/extensions, without implicit file writes."""
    return document._source_json


def save_document_as(document: ConversationDocument, destination: Path) -> Path:
    """Atomically save to an explicit destination; preserve old data on failure."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".conversation-",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(serialize_document(document).encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    except OSError as error:
        raise DocumentIOError("Unable to save the conversation file.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination
