"""Project and preset safety acceptance: no models, network or source fetching."""

import json
from dataclasses import replace

import pytest

from tests.test_speaker_mapping import choice, document
from ttsapp import project_storage as storage
from ttsapp.audio_export import ExportSettings
from ttsapp.speaker_mapping import resolve_document


def project():
    return storage.new_project(
        document(),
        "edge",
        {"edge": {"a": "custom"}, "piper": {"b": "invalid"}},
        export_settings=ExportSettings("m4a", normalize=True),
        source_locator="Z:/missing/source.json",
        source_sha256="a" * 64,
    )


def test_roundtrip_embedded_source_identity_all_provider_maps_and_settings(tmp_path):
    snapshot = project()
    target = tmp_path / "saved.ttsproject.json"
    storage.save_project(snapshot, target)
    reopened = storage.load_project(target)
    assert reopened == snapshot
    assert reopened.document.document_id == snapshot.document.document_id
    assert reopened.document.revision == snapshot.document.revision
    assert reopened.document.to_dict() == snapshot.document.to_dict()
    assert reopened.assignments["piper"]["b"] == "invalid"
    with pytest.raises(TypeError):
        reopened.assignments["edge"]["a"] = "mutate"
    assert reopened.source_locator == "Z:/missing/source.json"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("document", {}),
        ("document_id", ""),
        ("revision", True),
        ("provider_id", "unknown"),
        ("assignments", []),
        ("assignments", {"edge": {"unknown": "voice"}}),
        ("assignments", {"edge": {"a": 3}}),
        ("export_settings", {"normalize": "yes"}),
        ("export_settings", {"channels": True}),
        ("text_settings", {"max_chunk_characters": 20.0}),
        ("text_settings", {"sentence_pause_seconds": 8}),
        ("speed", True),
        ("speed", 0.1),
        ("source", {"sha256": "bad"}),
    ],
)
def test_invalid_project_is_rejected(key, value):
    data = storage.project_to_data(project())
    data[key] = value
    with pytest.raises(ValueError):
        storage.project_from_data(data)


@pytest.mark.parametrize("stage", ["fsync", "replace"])
def test_atomic_failure_preserves_destination_and_cleans_temporary(
    tmp_path, monkeypatch, stage
):
    target = tmp_path / "saved.json"
    target.write_bytes(b"previous")

    def fail(*args):
        raise OSError("Injected publication failure")

    monkeypatch.setattr(storage.os, stage, fail)
    with pytest.raises(OSError):
        storage.save_project(project(), target)
    assert target.read_bytes() == b"previous"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["saved.json"]


def test_file_limits_duplicates_depth_and_nonfinite(tmp_path):
    path = tmp_path / "file.json"
    for source in ('{"a":1,"a":2}', '{"x": NaN}', "[" * 66 + "0" + "]" * 66):
        path.write_text(source, encoding="utf-8")
        with pytest.raises(ValueError):
            storage.read_json_file(path)
    path.write_bytes(b" " * (storage.MAX_PROJECT_BYTES + 1))
    with pytest.raises(ValueError, match="size"):
        storage.load_project(path)


def test_preset_exact_matching_and_manual_preservation(tmp_path):
    data = {
        "schema_version": 1,
        "preferences": [
            {
                "role": " SAME ",
                "provider_id": "piper",
                "locale": "en-US",
                "voice_id": "us2",
            }
        ],
    }
    preferences = storage.preset_from_data(data)
    assert preferences == {("same", "piper", "en-US"): "us2"}
    target = tmp_path / "preset.json"
    storage.save_preset(preferences, target)
    assert storage.preset_from_data(storage.read_json_file(target)) == preferences
    provider = replace(choice(), provider_id="piper")
    resolved = resolve_document(
        document(), provider, preferences=preferences, current={"a": "gb"}
    )
    assert resolved.assignments[0].voice_id == "gb"
    assert resolved.assignments[1].voice_id == "us2"
    assert (
        resolve_document(document(), provider, preferences=preferences, locale="en-GB")
        .assignments[0]
        .voice_id
        == "gb"
    )
    data["preferences"].append(data["preferences"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        storage.preset_from_data(data)


def test_depth_64_document_can_be_embedded_in_project(tmp_path):
    doc = document()
    data = doc.to_dict()
    nested = {}
    data["extension"] = nested
    for _ in range(62):
        nested["child"] = {}
        nested = nested["child"]
    doc = doc.with_data(data)
    saved = storage.new_project(doc, "edge", {})
    path = tmp_path / "deep.json"
    storage.save_project(saved, path)
    assert storage.load_project(path).document.to_dict() == data


def test_mapping_file_contract():
    doc = document()
    valid = {"schema_version": 1, "provider_id": "edge", "voices": {"a": "custom"}}
    assert storage.validate_voice_map(valid, doc) == ("edge", {"a": "custom"})
    with pytest.raises(ValueError, match="explicit provider"):
        storage.validate_voice_map(valid, doc, "piper")
    valid["voices"]["unknown"] = "voice"
    with pytest.raises(ValueError, match="undeclared"):
        storage.validate_voice_map(valid, doc)


def test_project_serialization_never_opens_provenance(tmp_path, monkeypatch):
    snapshot = project()
    # The locator remains inert even when it looks like a URL or a command.
    data = storage.project_to_data(snapshot)
    data["source"]["locator"] = "https://example.invalid/private?command=ignored"
    result = storage.project_from_data(data)
    assert result.document.to_dict() == snapshot.document.to_dict()
    assert json.loads(json.dumps(storage.project_to_data(result)))["source"][
        "locator"
    ].startswith("https:")
