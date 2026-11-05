"""Data-only project snapshots and opt-in reusable mapping presets."""

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import TypeVar
from uuid import uuid4

from .audio_export import ExportSettings
from .conversation_document import (
    ConversationDocument,
    decode_json_value,
    parse_document_data,
)
from .text_processing import TextProcessingSettings

MAX_PROJECT_BYTES = 16 * 1024 * 1024
PROVIDERS = frozenset({"edge", "piper", "kokoro"})
SettingsType = TypeVar("SettingsType", ExportSettings, TextProcessingSettings)


@dataclass(frozen=True)
class ProjectSnapshot:
    """Validated embedded dialogue; provenance never replaces the saved snapshot."""

    project_id: str
    document: ConversationDocument
    provider_id: str
    assignments: Mapping[str, Mapping[str, str]]
    export_settings: ExportSettings
    text_settings: TextProcessingSettings
    locale: str = "en-US"
    speed: float | None = None
    source_locator: str | None = None
    source_sha256: str | None = None


def read_json_file(path: Path, *, limit: int = MAX_PROJECT_BYTES) -> object:
    """Read at most the declared bound, including when a file grows during read."""
    with path.open("rb") as source:
        if os.fstat(source.fileno()).st_size > limit:
            raise ValueError("JSON file exceeds its size limit.")
        raw = source.read(limit + 1)
    return decode_json_value(raw, max_bytes=limit, max_depth=65)


def write_json_atomic(
    data: object, destination: Path, *, limit: int = MAX_PROJECT_BYTES
) -> Path:
    """Flush and atomically publish explicit data, preserving old files on failure."""
    raw = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2).encode(
        "utf-8"
    )
    if len(raw) > limit:
        raise ValueError("JSON file exceeds its size limit.")
    decode_json_value(raw, max_bytes=limit, max_depth=65)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=".tts-save-",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    return value


def _string(value: object, label: str, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or (not empty and not value.strip())
        or len(value) > 4096
    ):
        raise ValueError(f"{label} must be a bounded string.")
    return value


def _version(data: dict) -> None:
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported snapshot schema_version; expected integer 1.")


def _provider(value: object) -> str:
    if not isinstance(value, str) or value not in PROVIDERS:
        raise ValueError("provider_id must be edge, piper or kokoro.")
    return value


def validate_voice_map(
    data: object, document: ConversationDocument, provider_id: str | None = None
) -> tuple[str, dict[str, str]]:
    """Validate the CLI map contract without model access or voice substitution."""
    root = _object(data, "Voice map")
    _version(root)
    provider = _provider(root.get("provider_id"))
    if provider_id is not None and provider != provider_id:
        raise ValueError("Voice-map provider does not match the explicit provider.")
    voices = _object(root.get("voices"), "voices")
    declared = {speaker.id for speaker in document.speakers}
    result = {}
    for key, value in voices.items():
        if key not in declared:
            raise ValueError("Voice map contains an undeclared speaker ID.")
        result[key] = _string(value, "Voice ID", empty=True)
    return provider, result


def new_project(
    document: ConversationDocument,
    provider_id: str,
    assignments: Mapping[str, Mapping[str, str]],
    *,
    export_settings: ExportSettings | None = None,
    text_settings: TextProcessingSettings | None = None,
    locale: str = "en-US",
    speed: float | None = None,
    source_locator: str | None = None,
    source_sha256: str | None = None,
) -> ProjectSnapshot:
    """Capture data explicitly; no source path is opened or fetched."""
    snapshot = ProjectSnapshot(
        project_id=uuid4().hex,
        document=document,
        provider_id=provider_id,
        assignments=assignments,
        export_settings=export_settings or ExportSettings(),
        text_settings=text_settings or TextProcessingSettings(),
        locale=locale,
        speed=speed,
        source_locator=source_locator,
        source_sha256=source_sha256,
    )
    return project_from_data(project_to_data(snapshot))


def project_to_data(project: ProjectSnapshot) -> dict:
    """Return an isolated serializable version-one project tree."""
    return {
        "schema_version": 1,
        "project_id": project.project_id,
        "document_id": project.document.document_id,
        "revision": project.document.revision,
        "document": project.document.to_dict(),
        "provider_id": project.provider_id,
        "assignments": {
            provider: dict(voices) for provider, voices in project.assignments.items()
        },
        "export_settings": asdict(project.export_settings),
        "text_settings": asdict(project.text_settings),
        "speed": project.speed,
        "locale": project.locale,
        "source": {"locator": project.source_locator, "sha256": project.source_sha256},
    }


def _settings(value: object, model: type[SettingsType]) -> SettingsType:
    data = _object(value, "Settings")
    allowed = model.__dataclass_fields__
    if set(data) - set(allowed):
        raise ValueError("Unknown settings field.")
    # Dataclasses validate ranges; JSON types must not coerce booleans/strings.
    for key, item in data.items():
        if key in {"normalize", "overwrite"}:
            if type(item) is not bool:
                raise ValueError(f"{key} must be boolean.")
        elif key == "audio_format":
            _string(item, key)
        elif key in {
            "sample_rate",
            "channels",
            "mp3_bitrate_kbps",
            "max_chunk_characters",
        }:
            if item is not None and type(item) is not int:
                raise ValueError(f"{key} must be an integer.")
        elif item is not None and type(item) not in (int, float):
            raise ValueError(f"{key} must be numeric.")
    try:
        return model(**data)
    except TypeError as error:
        raise ValueError("Malformed settings.") from error


def project_from_data(data: object) -> ProjectSnapshot:
    """Validate the entire project before callers replace any active state."""
    root = _object(data, "Project")
    _version(root)
    project_id = _string(root.get("project_id"), "project_id")
    document_id = _string(root.get("document_id"), "document_id")
    revision = root.get("revision")
    if type(revision) is not int or not 0 <= revision <= 2**53:
        raise ValueError("revision must be a nonnegative bounded integer.")
    document = replace(
        parse_document_data(root.get("document")),
        document_id=document_id,
        revision=revision,
    )
    provider_id = _provider(root.get("provider_id"))
    assignments = {}
    for provider, voices in _object(root.get("assignments"), "assignments").items():
        _, validated = validate_voice_map(
            {
                "schema_version": 1,
                "provider_id": provider,
                "voices": voices,
            },
            document,
        )
        assignments[provider] = MappingProxyType(validated)
    source = _object(root.get("source", {}), "source")
    locator = source.get("locator")
    digest = source.get("sha256")
    if locator is not None:
        _string(locator, "source locator")
    if digest is not None and (
        not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)
    ):
        raise ValueError("source sha256 must contain 64 lowercase hexadecimal digits.")
    speed = root.get("speed")
    if speed is not None and (type(speed) not in (int, float) or not 0.5 <= speed <= 2):
        raise ValueError("speed must be between 0.5 and 2.0.")
    return ProjectSnapshot(
        project_id=project_id,
        document=document,
        provider_id=provider_id,
        assignments=MappingProxyType(assignments),
        export_settings=_settings(root.get("export_settings", {}), ExportSettings),
        text_settings=_settings(root.get("text_settings", {}), TextProcessingSettings),
        locale=_string(root.get("locale", "en-US"), "locale"),
        speed=speed,
        source_locator=locator,
        source_sha256=digest,
    )


def load_project(path: Path) -> ProjectSnapshot:
    """Open the embedded snapshot without consulting its source locator."""
    return project_from_data(read_json_file(path))


def save_project(project: ProjectSnapshot, path: Path) -> Path:
    """Validate and atomically save an explicit project destination."""
    data = project_to_data(project_from_data(project_to_data(project)))
    return write_json_atomic(data, path)


def preset_from_data(data: object) -> dict[tuple[str, str, str], str]:
    """Match exact stripped/casefolded display role plus provider and locale."""
    root = _object(data, "Preset")
    _version(root)
    items = root.get("preferences")
    if not isinstance(items, list) or len(items) > 3000:
        raise ValueError("preferences must be an array of at most 3000 entries.")
    result = {}
    for item in items:
        record = _object(item, "Preference")
        key = (
            _string(record.get("role"), "Role").strip().casefold(),
            _provider(record.get("provider_id")),
            _string(record.get("locale"), "Locale"),
        )
        if key in result:
            raise ValueError("Duplicate role/provider/locale preference.")
        result[key] = _string(record.get("voice_id"), "Voice ID")
    return result


def save_preset(preferences: Mapping[tuple[str, str, str], str], path: Path) -> Path:
    """Save preferences only; never mutate source defaults or active overrides."""
    data = {
        "schema_version": 1,
        "preferences": [
            {"role": role, "provider_id": provider, "locale": locale, "voice_id": voice}
            for (role, provider, locale), voice in preferences.items()
        ],
    }
    preset_from_data(data)
    return write_json_atomic(data, path)
