"""Exact, reviewable CLI casting using catalog metadata, without an LLM call."""

import re
from collections.abc import Callable

from .conversation_document import ConversationDocument
from .provider_manager import ProviderChoice
from .providers.base import VoiceMetadata


def parse_voice_assignments(
    values: object,
) -> tuple[dict[str, str], dict[str, str]]:
    """Accept legacy voice strings or explicit provider/voice pairs."""
    if not isinstance(values, dict):
        raise ValueError("Voices must be an object keyed by speaker ID.")
    voices = {}
    providers = {}
    for speaker, value in values.items():
        if not isinstance(speaker, str):
            raise ValueError("Speaker IDs must be strings.")
        if isinstance(value, dict):
            if value.keys() != {"provider", "voice"} or any(
                not isinstance(part, str) or not part.strip() for part in value.values()
            ):
                raise ValueError(
                    "Each cast override needs exact provider and voice IDs."
                )
            providers[speaker] = value["provider"]
            value = value["voice"]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Voice IDs must be nonempty strings.")
        voices[speaker] = value
    return voices, providers


def _preference(raw: object) -> dict:
    if not isinstance(raw, dict) or raw.keys() - {"locale", "language", "required"}:
        raise ValueError("Casting preferences accept locale, language and required.")
    if type(raw.get("required", False)) is not bool or any(
        not isinstance(raw[key], str) or not raw[key].strip()
        for key in ("locale", "language")
        if key in raw
    ):
        raise ValueError("Specify locale/language strings and a boolean required flag.")
    if raw.get("required") and not (raw.get("locale") or raw.get("language")):
        raise ValueError("Required casting needs a locale or language.")
    return raw


def _matches(voice: VoiceMetadata, preference: dict) -> bool:
    locale = voice.language.casefold()
    requested_locale = preference.get("locale", "").casefold()
    language = preference.get("language", "").casefold()
    return (not requested_locale or locale == requested_locale) and (
        not language or locale.split("-")[0] == language
    )


def resolve_cli_cast(
    document: ConversationDocument,
    choices: tuple[ProviderChoice, ...],
    default_provider: str,
    assigned: dict[str, str],
    overrides: dict[str, str],
    raw: dict,
    ready: Callable[[ProviderChoice, VoiceMetadata], bool],
) -> tuple[dict[str, str], dict[str, dict]]:
    """Honor exact assignments, constraints, then preferences and distinctness.

    Locale is catalog evidence, not an inferred acoustic accent. Descriptions
    are supplied to Codex for judgment; this deterministic resolver does not
    invent timbre attributes or call a model.
    """
    providers = {choice.provider_id: choice for choice in choices}
    speakers = {speaker.id for speaker in document.speakers}
    per_speaker = raw.get("speaker_preferences", {})
    notes = raw.get("casting_notes", {})
    if not isinstance(per_speaker, dict) or not isinstance(notes, dict):
        raise ValueError("Speaker preferences and casting notes must be objects.")
    if (assigned.keys() | per_speaker.keys() | notes.keys()) - speakers:
        raise ValueError("Unknown speaker assignment or preference.")
    if any(not isinstance(note, str) for note in notes.values()):
        raise ValueError("Casting notes must be strings.")
    global_preference = _preference(
        {key: raw[key] for key in ("locale", "required") if key in raw}
    )
    preferences = {}
    for speaker in speakers:
        preference = per_speaker.get(speaker, {})
        if not isinstance(preference, dict):
            raise ValueError("Each speaker preference must be an object.")
        preferences[speaker] = _preference({**global_preference, **preference})
    cast = {}
    origins = {}
    catalogs = {}
    for speaker in document.speakers:
        provider_id = overrides.get(speaker.id, default_provider)
        if provider_id not in providers:
            raise ValueError(f"Unknown provider {provider_id} for {speaker.id}.")
        choice = providers[provider_id]
        if raw.get("offline", not providers[default_provider].online) and choice.online:
            raise ValueError("Offline casting excludes Edge and all online providers.")
        catalogs[speaker.id] = {voice.voice_id: voice for voice in choice.voices}
        explicit = assigned.get(speaker.id)
        origin = "Explicit direction assignment"
        if explicit is None:
            explicit = speaker.voice_defaults.get(provider_id)
            origin = "Explicit source default"
        if explicit is not None:
            if explicit not in catalogs[speaker.id]:
                raise ValueError(
                    f"Unknown {provider_id} voice for {speaker.id}: {explicit}"
                )
            cast[speaker.id] = explicit
            origins[speaker.id] = origin
    used = {
        (overrides.get(speaker, default_provider), voice)
        for speaker, voice in cast.items()
    }
    reports = {}
    for speaker in document.speakers:
        provider_id = overrides.get(speaker.id, default_provider)
        choice = providers[provider_id]
        preference = preferences[speaker.id]
        if speaker.id not in cast:
            candidates = [v for v in choice.voices if ready(choice, v)]
            matches = [v for v in candidates if _matches(v, preference)]
            if matches:
                candidates = matches
            elif preference.get("required"):
                raise ValueError(
                    f"Required locale/language unavailable for {speaker.id}."
                )
            if not candidates:
                raise ValueError(f"No ready voices for {speaker.id} in {provider_id}.")
            candidates.sort(
                key=lambda v: (
                    bool(speaker.gender) and v.gender != speaker.gender,
                    (provider_id, v.voice_id) in used,
                    v.language != "en-GB",
                    v.voice_id,
                )
            )
            cast[speaker.id] = candidates[0].voice_id
            origins[speaker.id] = "Catalog metadata selection"
            used.add((provider_id, cast[speaker.id]))
        voice = catalogs[speaker.id][cast[speaker.id]]
        matched = _matches(voice, preference)
        if preference.get("required") and not matched:
            raise ValueError(f"Required locale/language unavailable for {speaker.id}.")
        if not ready(choice, voice):
            raise ValueError(
                f"Required voice assets/runtime unavailable: {provider_id}/{voice.voice_id}. "
                "Run director discover; install the provider runtime and verify "
                "its model in Model library."
            )
        judgments = []
        description = (
            f"{speaker.description} {speaker.voice_direction} "
            f"{notes.get(speaker.id, '')}"
        )
        for attribute in ("warm", "authoritative", "friendly", "calm", "deep"):
            if re.search(rf"\b{attribute}\b", description, re.IGNORECASE):
                judgments.append(f"{attribute}: judgment call; no catalog attribute")
        reports[speaker.id] = {
            "provider": provider_id,
            "voice": voice.voice_id,
            "model_id": voice.model_id,
            "origin": origins[speaker.id],
            "requested": preference.get("locale"),
            "requested_language": preference.get("language"),
            "required": preference.get("required", False),
            "language": voice.language,
            "matched": matched,
            "match_evidence": {
                "field": "VoiceMetadata.language",
                "catalog_locale": voice.language,
            },
            "gender": voice.gender,
            "readiness": "online_unchecked"
            if choice.online
            else "local_assets_verified",
            "fallback": None
            if matched
            else "Optional locale/language preference unmet; assignment retained",
            "judgment_calls": judgments,
            "casting_note": notes.get(speaker.id, ""),
        }
    for speaker, report in reports.items():
        report["reused_with"] = [
            other
            for other, row in reports.items()
            if other != speaker
            and (row["provider"], row["voice"]) == (report["provider"], report["voice"])
        ]
    return cast, reports
