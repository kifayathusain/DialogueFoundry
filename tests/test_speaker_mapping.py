"""Offline assignment precedence, identity and settings acceptance."""

from pathlib import Path

import pytest

from ttsapp.conversation_document import load_document, parse_document_data
from ttsapp.provider_manager import ProviderChoice
from ttsapp.providers.base import VoiceMetadata
from ttsapp.speaker_mapping import MappingState, resolve_document


def document():
    return parse_document_data(
        {
            "speakers": [
                {"id": "a", "role": "Same", "voice_defaults": {"local": "bad"}},
                {"id": "b", "role": "Same"},
                {"id": "unused", "role": "Unused"},
            ],
            "segments": [{"speaker": "a", "text": "Dialogue: only."}],
        }
    )


def choice(provider="local", speed=True):
    return ProviderChoice(
        provider,
        provider,
        (
            VoiceMetadata("us1", "One", "en-US", "m1"),
            VoiceMetadata("gb", "Two", "en-GB", "m2"),
            VoiceMetadata("us2", "Three", "en-US", "m3"),
        ),
        provider == "edge",
        speed,
    )


def test_sample_defaults_shared_edge_and_summary():
    sample = load_document(Path("docs/tts-sample.json"))
    edge = ProviderChoice("edge", "Edge", choice().voices[:2], True, False)
    result = resolve_document(sample, edge)
    assert len(result.assignments) == 3
    assert all(item.voice_id for item in result.assignments)
    assert not result.errors
    assert result.silence_seconds == 84
    assert result.segments[-1].pause_after_seconds == 30
    assert any(item.code == "shared_voice" for item in result.diagnostics)
    assert all("note only" in item.direction_status for item in result.segments)


def test_precedence_and_invalid_explicit_are_visible():
    doc = document()
    settings = dict(
        project={"a": "gb"}, preferences={("same", "local", "en-US"): "us2"}
    )
    assert (
        resolve_document(doc, choice(), **settings).assignments[0].origin == "project"
    )
    result = resolve_document(doc, choice(), current={"a": "invalid"}, **settings)
    assert result.assignments[0].voice_id == "invalid"
    assert result.errors[0].code == "invalid_assignment"
    result = resolve_document(doc, choice(), preferences=settings["preferences"])
    assert result.assignments[0].voice_id == "us2"
    assert any(item.code == "invalid_hint" for item in result.diagnostics)
    data = doc.to_dict()
    data["speakers"][0]["voice_defaults"]["local"] = "gb"
    assert (
        resolve_document(doc.with_data(data), choice(), **settings)
        .assignments[0]
        .voice_id
        == "gb"
    )


def test_rank_locale_presence_unused_and_unused_role_readiness():
    doc = document()
    result = resolve_document(doc, choice(), file_present=lambda model: model == "m3")
    assert [item.voice_id for item in result.assignments] == ["us2", "us2", "us2"]
    assert not result.errors
    absent = resolve_document(doc, choice(), file_present=lambda model: False)
    assert [item.voice_id for item in absent.assignments] == ["us1", "us2", "us1"]
    assert len(absent.errors) == 1
    assert "Model library" in absent.errors[0].message
    assert absent == resolve_document(doc, choice(), file_present=lambda model: False)


def test_identity_reorder_provider_restore_delete_and_reset():
    doc = document()
    state = MappingState()
    state.set_voice(doc, "a", "local", "gb")
    state.set_voice(doc, "b", "edge", "custom")
    assert state.selections(doc, "edge") == {"b": "custom"}
    data = doc.to_dict()
    data["speakers"].reverse()
    edited = doc.with_data(data)
    assert state.selections(edited, "local") == {"a": "gb"}
    assert state.selections(document(), "local") == {}
    state.set_voice(doc, "b", "local", "invalid")
    state.reset_unmapped(doc, choice())
    assert state.selections(doc, "local") == {"a": "gb"}
    data["speakers"] = [item for item in data["speakers"] if item["id"] != "b"]
    state.reconcile(doc.with_data(data))
    assert state.selections(doc, "edge") == {}
    state.reset_role(doc, "a", "local")
    assert state.selections(doc, "local") == {}


@pytest.mark.parametrize(
    ("segment", "role", "job", "expected", "source"),
    [
        (1.2, 1.3, 1.4, 1.2, "segment"),
        (None, 1.3, 1.4, 1.3, "role"),
        (None, None, 1.4, 1.4, "job"),
        (None, None, None, None, "provider"),
    ],
)
def test_speed_precedence(segment, role, job, expected, source):
    doc = document()
    data = doc.to_dict()
    if segment is not None:
        data["segments"][0]["speech"] = {"speed": segment}
    if role is not None:
        data["speakers"][0]["speech"] = {"speed": role}
    result = resolve_document(doc.with_data(data), choice(), job_speed=job)
    assert (result.segments[0].speed, result.segments[0].speed_source) == (
        expected,
        source,
    )
    edge = resolve_document(doc.with_data(data), choice("edge", False), job_speed=job)
    assert bool(edge.errors) == (expected is not None)


@pytest.mark.parametrize("speed", [True, "1", float("nan"), float("inf"), 0.4, 2.1])
def test_invalid_job_speed(speed):
    assert resolve_document(document(), choice(), job_speed=speed).errors


def test_custom_edge_and_unused_invalid_are_not_blocking():
    result = resolve_document(
        document(), choice("edge", False), current={"a": "custom", "unused": ""}
    )
    assert not result.errors
    assert result.assignments[0].voice_id == "custom"
