"""Catalog-backed Director casting and review, without inference from names."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .conversation_document import ConversationDocument, DocumentSpeaker
from .provider_manager import ProviderChoice


def speaker_gender(speaker: DocumentSpeaker) -> tuple[str | None, str]:
    """Use explicit metadata only; conflicting descriptions require review."""
    supplied = speaker.gender.strip().casefold()
    if supplied not in {"male", "female"}:
        return None, "Gender missing or not a supported male/female match"
    notes = f"{speaker.description} {speaker.voice_direction}".casefold()
    opposite = "female" if supplied == "male" else "male"
    if re.search(rf"\b{opposite}\b", notes):
        return None, "Contradictory gender metadata; review the source"
    return supplied, ""


def match_cast(
    document: ConversationDocument,
    choice: ProviderChoice,
    cast: tuple[tuple[str, str], ...],
    *,
    locked: frozenset[str] = frozenset(),
) -> tuple[tuple[str, str], ...]:
    """Prefer verifiable compatible voices, preserving explicit/manual choices."""
    selected = dict(cast)
    known = {voice.voice_id: voice for voice in choice.voices}
    used = {
        selected.get(speaker.id, "")
        for speaker in document.speakers
        if speaker_gender(speaker)[0] is None
        or (
            selected.get(speaker.id) in known
            and known[selected[speaker.id]].gender == speaker_gender(speaker)[0]
        )
    }
    for speaker in document.speakers:
        if speaker.id in locked:
            continue
        explicit = speaker.voice_defaults.get(choice.provider_id)
        if explicit:
            selected[speaker.id] = explicit
            used.add(explicit)
            continue
        gender, _ = speaker_gender(speaker)
        if gender is None:
            continue
        current = known.get(selected.get(speaker.id, ""))
        if current and current.gender == gender:
            continue
        candidates = [voice for voice in choice.voices if voice.gender == gender]
        if candidates:
            candidates.sort(
                key=lambda voice: (
                    voice.language != (current.language if current else "en-GB"),
                    voice.voice_id in used,
                    voice.voice_id,
                )
            )
            selected[speaker.id] = candidates[0].voice_id
            used.add(candidates[0].voice_id)
    return tuple(selected.items())


@dataclass(frozen=True)
class CastReview:
    """One source speaker's visible assignment and its verifiable rationale."""

    speaker_id: str
    gender: str
    provider_id: str
    voice_id: str
    voice_name: str
    locale: str
    origin: str
    reason: str
    needs_review: bool


def review_cast(
    document: ConversationDocument,
    choice: ProviderChoice,
    cast: tuple[tuple[str, str], ...],
    *,
    manual: frozenset[str] = frozenset(),
    ai: bool = False,
) -> tuple[CastReview, ...]:
    """Describe each assignment, including unknown or incompatible metadata."""
    known = {voice.voice_id: voice for voice in choice.voices}
    rows = []
    for speaker in document.speakers:
        voice_id = dict(cast).get(speaker.id, "")
        voice = known.get(voice_id)
        gender, uncertainty = speaker_gender(speaker)
        origin = "Catalog match"
        if speaker.id in manual:
            origin = "Manual override"
        elif speaker.voice_defaults.get(choice.provider_id) == voice_id:
            origin = "Explicit source assignment"
        elif ai:
            origin = "AI match"
        if voice is None:
            uncertainty = "Voice unavailable in this provider's catalog"
        elif gender and voice.gender != gender:
            uncertainty = "Compatible voice gender cannot be verified"
        reason = uncertainty or f"Catalog confirms {gender} voice for supplied metadata"
        rows.append(
            CastReview(
                speaker.id,
                speaker.gender or "Not supplied",
                choice.provider_id,
                voice_id,
                voice.display_name if voice else "Unavailable",
                voice.language if voice else "Unknown",
                origin,
                reason,
                bool(uncertainty),
            )
        )
    return tuple(rows)
