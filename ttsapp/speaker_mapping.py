"""Pure stable role assignments and structured request preflight."""

import math
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .conversation_document import ConversationDocument, DocumentDiagnostic
from .provider_manager import ProviderChoice


@dataclass(frozen=True)
class VoiceAssignment:
    """An explicit or automatic selection; file presence is only a hint."""

    speaker_id: str
    provider_id: str
    voice_id: str
    origin: str
    readiness: str = "Verification required in generation worker"


@dataclass(frozen=True)
class ResolvedSegment:
    """Dialogue-only synthesis input with source identity and effective settings."""

    document_id: str
    revision: int
    index: int
    speaker_id: str
    voice_id: str
    text: str
    speed: float | None
    speed_source: str
    pause_after_seconds: float
    direction_status: str
    provider_id: str = ""


@dataclass(frozen=True)
class Preflight:
    """Metadata-only summary; words are counted by whitespace splitting."""

    assignments: tuple[VoiceAssignment, ...]
    segments: tuple[ResolvedSegment, ...]
    diagnostics: tuple[DocumentDiagnostic, ...]
    role_count: int
    used_role_count: int
    word_count: int
    silence_seconds: float

    @property
    def errors(self) -> tuple[DocumentDiagnostic, ...]:
        """Return blocking diagnostics."""
        return tuple(item for item in self.diagnostics if item.severity == "error")


class MappingState:
    """Store explicit edits by document, speaker and provider, never row number."""

    def __init__(self) -> None:
        self._edits: dict[tuple[str, str, str], str] = {}

    def set_voice(
        self,
        document: ConversationDocument,
        speaker_id: str,
        provider_id: str,
        voice_id: str,
    ) -> None:
        """Retain even invalid explicit input for visible correction."""
        if speaker_id not in {speaker.id for speaker in document.speakers}:
            raise ValueError("Unknown speaker ID.")
        self._edits[document.document_id, speaker_id, provider_id] = voice_id

    def reconcile(self, document: ConversationDocument) -> None:
        """Remove deleted identities so future roles cannot inherit stale edits."""
        retained = {speaker.id for speaker in document.speakers}
        self._edits = {
            key: value
            for key, value in self._edits.items()
            if key[0] != document.document_id or key[1] in retained
        }

    def selections(
        self, document: ConversationDocument, provider_id: str
    ) -> dict[str, str]:
        """Return an isolated current-provider snapshot."""
        return {
            speaker: voice
            for (identity, speaker, provider), voice in self._edits.items()
            if identity == document.document_id and provider == provider_id
        }

    def reset_role(
        self, document: ConversationDocument, speaker_id: str, provider_id: str
    ) -> None:
        """Reset exactly one role/provider to its automatic default."""
        self._edits.pop((document.document_id, speaker_id, provider_id), None)

    def reset_unmapped(
        self, document: ConversationDocument, choice: ProviderChoice
    ) -> None:
        """Clear only invalid edits, preserving unrelated manual selections."""
        valid = {voice.voice_id for voice in choice.voices}
        for speaker, voice in self.selections(document, choice.provider_id).items():
            if not voice.strip() or (
                choice.provider_id != "edge" and voice not in valid
            ):
                self.reset_role(document, speaker, choice.provider_id)


def resolve_document(
    document: ConversationDocument,
    choice: ProviderChoice,
    *,
    current: Mapping[str, str] | None = None,
    project: Mapping[str, str] | None = None,
    preferences: Mapping[tuple[str, str, str], str] | None = None,
    locale: str = "en-US",
    file_present: Callable[[str], bool] | None = None,
    job_speed: float | None = None,
    speaker_choices: Mapping[str, ProviderChoice] | None = None,
) -> Preflight:
    """Resolve without loading models, discovery, downloads or widgets.

    Project assignments must belong to this document; persistence validates that
    binding. Preference keys use stripped, casefolded role, provider and locale.
    """
    current = current or {}
    project = project or {}
    preferences = preferences or {}
    diagnostics = list(document.diagnostics)
    used = {segment.speaker for segment in document.segments}
    default_choice = choice
    speaker_choices = speaker_choices or {}
    assignments = []
    selected: Counter[tuple[str, str]] = Counter()

    def valid(voice: str) -> bool:
        return bool(voice.strip()) and (choice.provider_id == "edge" or voice in known)

    def warn(code: str, path: str, message: str, error: bool = False) -> None:
        diagnostics.append(
            DocumentDiagnostic(code, path, message, "error" if error else "warning")
        )

    for index, speaker in enumerate(document.speakers):
        choice = speaker_choices.get(speaker.id, default_choice)
        known = {voice.voice_id: voice for voice in choice.voices}
        path = f"$.speakers[{index}]"
        voice_id = ""
        origin = "catalog"
        explicit = False
        for source, values in (("manual", current), ("project", project)):
            if speaker.id in values:
                voice_id = values[speaker.id]
                origin = source
                explicit = True
                break
        if not explicit:
            candidates = (
                ("imported", speaker.voice_defaults.get(choice.provider_id)),
                (
                    "preference",
                    preferences.get(
                        (speaker.role.strip().casefold(), choice.provider_id, locale)
                    ),
                ),
            )
            for source, candidate in candidates:
                if candidate is None:
                    continue
                if valid(candidate):
                    voice_id, origin = candidate, source
                    break
                warn("invalid_hint", path, f"Invalid {source} voice hint ignored.")
            if not voice_id and choice.voices:
                ranked = sorted(
                    enumerate(choice.voices),
                    key=lambda item: (
                        item[1].language != locale,
                        not (
                            file_present
                            and item[1].model_id
                            and file_present(item[1].model_id)
                        ),
                        selected[choice.provider_id, item[1].voice_id] > 0,
                        item[0],
                    ),
                )
                voice_id = ranked[0][1].voice_id
        readiness = "Verification required in generation worker"
        if not valid(voice_id):
            readiness = "Select a valid voice"
            warn(
                "invalid_assignment",
                path,
                f"Select a valid voice for {speaker.id}.",
                speaker.id in used,
            )
        elif voice_id in known and known[voice_id].model_id and file_present:
            if not file_present(known[voice_id].model_id):
                readiness = "Install and verify model in Model library"
                warn(
                    "missing_model",
                    path,
                    f"{speaker.id}: {readiness}.",
                    speaker.id in used,
                )
        assignments.append(
            VoiceAssignment(speaker.id, choice.provider_id, voice_id, origin, readiness)
        )
        selected[choice.provider_id, voice_id] += 1
    for (provider_id, voice), count in selected.items():
        if voice and count > 1:
            roles = ", ".join(
                item.speaker_id
                for item in assignments
                if item.voice_id == voice and item.provider_id == provider_id
            )
            warn(
                "shared_voice",
                "$.speakers",
                f"Shared voice for roles {roles}; distinct delivery is not guaranteed.",
            )
    voices = {item.speaker_id: item.voice_id for item in assignments}
    speakers = {speaker.id: speaker for speaker in document.speakers}
    segments = []
    for index, segment in enumerate(document.segments, 1):
        choice = speaker_choices.get(segment.speaker, default_choice)
        role = speakers[segment.speaker]
        speed = None
        source = "provider"
        for name, value in (
            ("segment", segment.speech.speed),
            ("role", role.speech.speed),
            ("job", job_speed),
        ):
            if value is not None:
                speed, source = value, name
                break
        if speed is not None:
            if (
                isinstance(speed, bool)
                or not isinstance(speed, (int, float))
                or not math.isfinite(speed)
                or not 0.5 <= speed <= 2
            ):
                warn(
                    "invalid_speed",
                    f"$.segments[{index - 1}].speech.speed",
                    "Speed must be between 0.5 and 2.0.",
                    True,
                )
            elif not choice.supports_speed:
                warn(
                    "unsupported_speed",
                    f"$.segments[{index - 1}].speech.speed",
                    "Selected provider does not support explicit speed.",
                    True,
                )
        direction = "No direction note"
        if role.voice_direction or segment.voice_direction:
            direction = "Direction is a note only; prose style is not applied"
            warn("direction_note", f"$.segments[{index - 1}]", direction)
        segments.append(
            ResolvedSegment(
                document.document_id,
                document.revision,
                index,
                segment.speaker,
                voices[segment.speaker],
                segment.text,
                speed,
                source,
                segment.pause_after_seconds,
                direction,
                choice.provider_id,
            )
        )
    return Preflight(
        tuple(assignments),
        tuple(segments),
        tuple(diagnostics),
        len(speakers),
        len(used),
        sum(len(segment.text.split()) for segment in document.segments),
        sum(segment.pause_after_seconds for segment in document.segments),
    )
