"""Offline contract tests: JSON only, no providers, models, media or widgets."""

import builtins
import copy
import importlib.util
import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ttsapp import conversation_document as documents
from ttsapp.conversation_document import (
    DocumentIOError,
    DocumentValidationError,
    load_document,
    parse_document_data,
    parse_document_text,
    save_document_as,
    serialize_document,
)

SAMPLE = Path(__file__).resolve().parents[1] / "docs" / "tts-sample.json"


def minimal() -> dict:
    """Return a fresh minimal source tree for each test."""
    return {
        "speakers": [{"id": "a", "role": "Role"}],
        "segments": [{"speaker": "a", "text": "Hello"}],
    }


def diagnostics(data: object) -> tuple[documents.DocumentDiagnostic, ...]:
    """Return semantic errors from invalid Python JSON trees."""
    with pytest.raises(DocumentValidationError) as caught:
        parse_document_data(data)
    return caught.value.diagnostics


def test_unmodified_sample_round_trips_with_final_pause() -> None:
    before = SAMPLE.read_bytes()
    document = load_document(SAMPLE)

    assert len(document.speakers) == 3
    assert len(document.segments) == 26
    assert sum(segment.pause_after_seconds for segment in document.segments) == 84
    assert document.segments[-1].pause_after_seconds == 30
    assert document.schema_version == 1
    assert document.diagnostics == ()
    assert json.loads(serialize_document(document)) == json.loads(before)
    assert SAMPLE.read_bytes() == before


def test_optional_fields_unicode_and_extensions_preserve_source() -> None:
    data = minimal()
    data["extra"] = {"list": [None, True, {"nested": 3.125}]}
    data["speakers"][0].update(
        role="  Same display role  ",
        voice_direction="Quiet: a note\nonly",
        voice_defaults={"piper": "catalog-id", "custom-provider": "voice-id"},
        speech={"speed": 0.75, "future": {"enabled": True}},
        metadata={"name": "Café"},
    )
    data["segments"][0].update(
        text='  Café: こんにちは\nLiteral {braces} and "quotes" \\  ',
        pause_after_seconds=0.125,
        voice_direction="Do not speak this note",
        speech={"speed": 1.125, "future": ["value"]},
        extra=False,
    )
    document = parse_document_text("\ufeff" + json.dumps(data, ensure_ascii=False))
    assert document.to_dict() == data
    assert json.loads(serialize_document(document)) == data
    assert document.segments[0].text == data["segments"][0]["text"]
    assert document.segments[0].pause_after_seconds == 0.125
    assert document.segments[0].speech.speed == 1.125
    assert document.speakers[0].speech.speed == 0.75
    assert document.speakers[0].voice_defaults["piper"] == "catalog-id"
    assert {item.path for item in document.diagnostics} == {
        "$.extra",
        "$.speakers[0].metadata",
        "$.speakers[0].speech.future",
        "$.segments[0].extra",
        "$.segments[0].speech.future",
    }
    assert all(item.severity == "warning" for item in document.diagnostics)


def test_file_bytes_and_python_tree_have_identical_semantics(tmp_path: Path) -> None:
    data = minimal()
    data["segments"][0]["text"] = "Café\nTime: 6:30"
    source = b"\xef\xbb\xbf" + json.dumps(data, ensure_ascii=False).encode("utf-8")
    path = tmp_path / "source.json"
    path.write_bytes(source)
    parsed = [
        load_document(path),
        parse_document_text(source),
        parse_document_data(data),
    ]
    assert all(item.to_dict() == data for item in parsed)
    assert len({item.document_id for item in parsed}) == 3
    assert len({item.content_hash for item in parsed}) == 1


def test_defaults_preserve_absence_and_explicit_zero() -> None:
    data = minimal()
    data["segments"].append({"speaker": "a", "text": "Next", "pause_after_seconds": 0})
    document = parse_document_data(data)
    assert [segment.pause_after_seconds for segment in document.segments] == [0, 0]
    assert document.speakers[0].voice_direction == ""
    assert document.segments[0].voice_direction == ""
    assert document.segments[0].speech.speed is None
    assert document.speakers[0].speech.speed is None
    assert document.to_dict() == data


def test_duplicate_roles_are_legal_but_ids_are_case_sensitive_and_unique() -> None:
    data = minimal()
    data["speakers"].append({"id": "A", "role": "Role"})
    document = parse_document_data(data)
    assert [speaker.id for speaker in document.speakers] == ["a", "A"]
    assert document.diagnostics[0].code == "unused_speaker"
    data["speakers"][1]["id"] = "a"
    assert any(item.code == "duplicate_id" for item in diagnostics(data))


@pytest.mark.parametrize("value", [True, False, None, "1", 1.0, 0, 2])
def test_invalid_versions_are_rejected_without_coercion(value: object) -> None:
    data = minimal()
    data["schema_version"] = value
    errors = diagnostics(data)
    assert errors[0].path == "$.schema_version"
    assert errors[0].code in {"invalid_type", "unsupported_version"}


@pytest.mark.parametrize("value", [None, [], "source", 3, True])
def test_non_object_roots_are_rejected(value: object) -> None:
    assert diagnostics(value)[0].path == "$"


@pytest.mark.parametrize("key", ["speakers", "segments"])
@pytest.mark.parametrize("value", [None, {}, "items", [], True])
def test_required_arrays_reject_wrong_types_and_empty_values(
    key: str, value: object
) -> None:
    data = minimal()
    data[key] = value
    assert diagnostics(data)[0].path == f"$.{key}"


@pytest.mark.parametrize("key", ["speakers", "segments"])
def test_missing_arrays_are_reported(key: str) -> None:
    data = minimal()
    del data[key]
    assert diagnostics(data)[0].code == "missing_field"


@pytest.mark.parametrize(
    ("array", "key"),
    [
        ("speakers", "id"),
        ("speakers", "role"),
        ("segments", "speaker"),
        ("segments", "text"),
    ],
)
@pytest.mark.parametrize("value", [None, True, 7, "", " \n "])
def test_required_strings_reject_invalid_values(
    array: str, key: str, value: object
) -> None:
    data = minimal()
    data[array][0][key] = value
    assert any(item.path == f"$.{array}[0].{key}" for item in diagnostics(data))


@pytest.mark.parametrize(
    ("array", "key"),
    [
        ("speakers", "id"),
        ("speakers", "role"),
        ("segments", "speaker"),
        ("segments", "text"),
    ],
)
def test_missing_required_strings_are_reported(array: str, key: str) -> None:
    data = minimal()
    del data[array][0][key]
    assert any(
        item.code == "missing_field" and item.path.endswith(f".{key}")
        for item in diagnostics(data)
    )


@pytest.mark.parametrize("array", ["speakers", "segments"])
@pytest.mark.parametrize("value", [None, [], True, "role"])
def test_array_elements_must_be_objects(array: str, value: object) -> None:
    data = minimal()
    data[array][0] = value
    assert diagnostics(data)[0].path == f"$.{array}[0]"


@pytest.mark.parametrize("array,key", [("speakers", "id"), ("segments", "speaker")])
@pytest.mark.parametrize("value", [" a", "a ", "\ta"])
def test_ids_are_not_silently_trimmed(array: str, key: str, value: str) -> None:
    data = minimal()
    data[array][0][key] = value
    assert any(item.code == "invalid_id" for item in diagnostics(data))


def test_unknown_reference_has_actionable_path() -> None:
    data = minimal()
    data["segments"][0]["speaker"] = "A"
    assert diagnostics(data)[0].code == "unknown_speaker"
    assert diagnostics(data)[0].path == "$.segments[0].speaker"


@pytest.mark.parametrize("array", ["speakers", "segments"])
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("voice_direction", None),
        ("voice_direction", 1),
        ("speech", None),
        ("speech", []),
        ("speech", {"speed": None}),
        ("speech", {"speed": True}),
        ("speech", {"speed": "1"}),
        ("speech", {"speed": 0.49}),
        ("speech", {"speed": 2.01}),
    ],
)
def test_known_optional_fields_cannot_hide_as_extensions(
    array: str, key: str, value: object
) -> None:
    data = minimal()
    data[array][0][key] = value
    assert any(
        item.path.startswith(f"$.{array}[0].{key}") for item in diagnostics(data)
    )


@pytest.mark.parametrize(
    "value",
    [None, [], {"edge": None}, {"edge": " "}, {" edge": "voice"}, {"edge": " voice"}],
)
def test_voice_defaults_are_typed_ids_without_provider_resolution(
    value: object,
) -> None:
    data = minimal()
    data["speakers"][0]["voice_defaults"] = value
    assert diagnostics(data)[0].path.startswith("$.speakers[0].voice_defaults")


@pytest.mark.parametrize("value", [None, True, False, "1", -0.01, 600.01])
def test_invalid_pause_values_are_rejected(value: object) -> None:
    data = minimal()
    data["segments"][0]["pause_after_seconds"] = value
    assert diagnostics(data)[0].path == "$.segments[0].pause_after_seconds"


@pytest.mark.parametrize("value", [0, 0.125, 600])
def test_pause_boundaries_round_trip(value: float) -> None:
    data = minimal()
    data["segments"][0]["pause_after_seconds"] = value
    assert parse_document_data(data).to_dict() == data


@pytest.mark.parametrize("value", [0.5, 1.125, 2])
def test_speed_boundaries_round_trip(value: float) -> None:
    data = minimal()
    data["speakers"][0]["speech"] = {"speed": value}
    data["segments"][0]["speech"] = {"speed": value}
    assert parse_document_data(data).to_dict() == data


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("location", ["pause", "speed", "extension"])
def test_nonfinite_numbers_at_every_depth_are_rejected(
    value: float, location: str
) -> None:
    data = minimal()
    if location == "pause":
        data["segments"][0]["pause_after_seconds"] = value
    elif location == "speed":
        data["speakers"][0]["speech"] = {"speed": value}
    else:
        data["extension"] = {"values": [value]}
    assert any(item.code == "non_finite_number" for item in diagnostics(data))


@pytest.mark.parametrize(
    ("source", "path"),
    [
        (' {"speakers":[],"speakers":[]}', "$.speakers"),
        ('{"speakers":[{"id":"a","id":"b"}],"segments":[]}', "$.speakers[0].id"),
        ('{"x":{"a":[{"z":1,"z":2}]}}', "$.x.a[0].z"),
        ('{"x":{"a":1,"\\u0061":2}}', "$.x.a"),
    ],
)
def test_duplicate_keys_include_paths_even_in_extensions(
    source: str, path: str
) -> None:
    with pytest.raises(DocumentValidationError) as caught:
        parse_document_text(source)
    assert any(
        item.code == "duplicate_key" and item.path == path
        for item in caught.value.diagnostics
    )


@pytest.mark.parametrize(
    "source", ['{\n "speakers": [}', '{"x":1,}', "", "[", '"private dialogue" extra']
)
def test_syntax_errors_have_line_column_without_source_dump(source: str) -> None:
    with pytest.raises(DocumentValidationError) as caught:
        parse_document_text(source)
    error = caught.value.diagnostics[0]
    assert error.code == "json_syntax"
    assert error.line is not None and error.column is not None
    assert "private dialogue" not in str(caught.value)


def nested(depth: int) -> object:
    """Build a nested extension with the requested number of containers."""
    value: object = "end"
    for _ in range(depth):
        value = [value]
    return value


def test_depth_boundary_and_quoted_braces() -> None:
    data = minimal()
    data["extension"] = nested(63)  # Root is container 1.
    data["segments"][0]["text"] = '{ [ " \\ ' * 100
    assert parse_document_data(data).to_dict() == data
    data["extension"] = nested(64)
    assert diagnostics(data)[0].code == "depth_limit"
    with pytest.raises(DocumentValidationError) as caught:
        parse_document_text(json.dumps(data))
    assert caught.value.diagnostics[0].code == "depth_limit"
    with pytest.raises(DocumentValidationError):
        parse_document_text("[" * 5000 + "]" * 5000)


def test_cyclic_and_non_json_python_trees_fail_cleanly() -> None:
    data = minimal()
    data["cycle"] = data
    assert diagnostics(data)[0].code == "depth_limit"
    for value in [{1: "bad key"}, {"value": {1, 2}}, {"value": (1, 2)}]:
        assert diagnostics(value)[0].code == "invalid_type"


@pytest.mark.parametrize("key,limit", [("speakers", 1000), ("segments", 10000)])
def test_count_boundaries(key: str, limit: int) -> None:
    data = minimal()
    if key == "speakers":
        data[key] = [{"id": f"id{index}", "role": "Role"} for index in range(limit)]
        data["segments"][0]["speaker"] = "id0"
    else:
        data[key] *= limit
    assert len(getattr(parse_document_data(data), key)) == limit
    data[key].append(data[key][-1])
    assert any(item.code == "count_limit" for item in diagnostics(data))


def test_total_silence_boundary() -> None:
    data = minimal()
    data["segments"] = [
        {"speaker": "a", "text": "Line", "pause_after_seconds": 600}
    ] * 144
    assert (
        sum(item.pause_after_seconds for item in parse_document_data(data).segments)
        == 86400
    )
    data["segments"].append(
        {"speaker": "a", "text": "Last", "pause_after_seconds": 0.001}
    )
    assert diagnostics(data)[0].code == "total_pause_limit"


def test_byte_limit_for_file_text_and_python_tree(tmp_path: Path) -> None:
    data = minimal()
    base_size = len(json.dumps(data, separators=(",", ":")).encode())
    data["segments"][0]["text"] += "x" * (documents.MAX_INPUT_BYTES - base_size)
    source = json.dumps(data, separators=(",", ":")).encode()
    assert len(source) == documents.MAX_INPUT_BYTES
    path = tmp_path / "large.json"
    path.write_bytes(source)
    assert len(serialize_document(load_document(path)).encode()) == len(source)
    assert parse_document_data(data).to_dict() == data
    path.write_bytes(source + b" ")
    for parse in [
        lambda: load_document(path),
        lambda: parse_document_text(source + b" "),
    ]:
        with pytest.raises(DocumentValidationError) as caught:
            parse()
        assert caught.value.diagnostics[0].code == "size_limit"
    data["segments"][0]["text"] += "é"  # UTF-8 bytes, not character count.
    assert diagnostics(data)[0].code == "size_limit"


def test_file_size_is_checked_before_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b"{}")
    real_fstat = documents.os.fstat

    class LargeStat:
        st_size = documents.MAX_INPUT_BYTES + 1

    class UnreadableSource:
        def __enter__(self) -> "UnreadableSource":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def fileno(self) -> int:
            return 0

        def read(self, size: int) -> bytes:
            pytest.fail("An oversized file must be rejected before reading")

    monkeypatch.setattr(Path, "open", lambda *args: UnreadableSource())
    monkeypatch.setattr(documents.os, "fstat", lambda descriptor: LargeStat())
    with pytest.raises(DocumentValidationError) as caught:
        load_document(path)
    assert caught.value.diagnostics[0].code == "size_limit"
    monkeypatch.setattr(documents.os, "fstat", real_fstat)


def test_semantic_errors_are_aggregated_and_bounded() -> None:
    data = minimal()
    data["segments"] = [{} for _ in range(80)]
    errors = diagnostics(data)
    assert len(errors) == 101
    assert errors[0].path == "$.segments[0].speaker"
    assert errors[1].path == "$.segments[0].text"
    assert errors[-1].code == "diagnostics_omitted"


def test_source_copy_isolation_and_identity_revision() -> None:
    data = minimal()
    data["extension"] = {"nested": [1]}
    data["speakers"][0]["voice_defaults"] = {"edge": "voice"}
    original = copy.deepcopy(data)
    document = parse_document_data(data)
    data["extension"]["nested"].append(2)
    data["segments"][0]["text"] = "mutated"
    extracted = document.to_dict()
    extracted["extension"]["nested"].append(3)
    assert document.to_dict() == original
    with pytest.raises(FrozenInstanceError):
        document.segments[0].text = "changed"
    with pytest.raises(TypeError):
        document.speakers[0].voice_defaults["edge"] = "changed"
    edited = document.with_data(data)
    assert edited.document_id == document.document_id
    assert edited.revision == 1 and document.revision == 0
    assert edited.content_hash != document.content_hash
    reloaded = parse_document_text(serialize_document(edited), reload_of=edited)
    assert reloaded.document_id == edited.document_id
    assert reloaded.revision == 2 and reloaded.content_hash == edited.content_hash
    imported = parse_document_data(data)
    assert imported.document_id != edited.document_id
    assert imported.revision == 0 and imported.content_hash == edited.content_hash


def test_explicit_save_preserves_imported_path(tmp_path: Path) -> None:
    source = tmp_path / "import.json"
    source.write_text(json.dumps(minimal()), encoding="utf-8")
    before = source.read_bytes()
    document = load_document(source)
    destination = tmp_path / "saved.json"
    assert save_document_as(document, destination) == destination
    assert source.read_bytes() == before
    assert load_document(destination).to_dict() == document.to_dict()
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "import.json",
        "saved.json",
    ]


@pytest.mark.parametrize("failure", ["replace", "flush"])
def test_atomic_save_failure_preserves_destination_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    destination = tmp_path / "saved.json"
    destination.write_bytes(b"previous")

    def fail(*args: object) -> None:
        raise OSError("Injected filesystem failure")

    monkeypatch.setattr(
        documents.os, "replace" if failure == "replace" else "fsync", fail
    )
    with pytest.raises(DocumentIOError):
        save_document_as(parse_document_data(minimal()), destination)
    assert destination.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [destination]


def test_missing_file_and_destination_report_io_errors(tmp_path: Path) -> None:
    with pytest.raises(DocumentIOError):
        load_document(tmp_path / "missing.json")
    with pytest.raises(DocumentIOError):
        save_document_as(
            parse_document_data(minimal()), tmp_path / "missing" / "saved.json"
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "source", [b"\xff", '"\ud800"', '{"x":"\\ud800"}', '{"\\ud800":1}']
)
def test_invalid_unicode_fails_cleanly(source: str | bytes) -> None:
    with pytest.raises(DocumentValidationError):
        parse_document_text(source)


def test_document_operations_do_not_import_provider_or_widget_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        assert not any(
            word in name
            for word in ("provider", "tkinter", "onnx", "edge_tts", "socket")
        )
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    spec = importlib.util.spec_from_file_location(
        "isolated_document", documents.__file__
    )
    isolated = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, isolated)
    spec.loader.exec_module(isolated)
    assert (
        isolated.parse_document_text(
            isolated.serialize_document(isolated.parse_document_data(minimal()))
        ).to_dict()
        == minimal()
    )


def test_example_and_published_schema_are_valid_json() -> None:
    docs = SAMPLE.parent
    example = load_document(docs / "tts-input-example.json")
    assert example.speakers[0].speech.speed == 0.9
    schema = json.loads((docs / "tts-input.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["segments"]["maxItems"] == documents.MAX_SEGMENTS
    assert schema["properties"]["speakers"]["maxItems"] == documents.MAX_SPEAKERS


def test_serialization_preserves_numeric_source_spelling_and_size() -> None:
    source = json.dumps(minimal())[:-1] + ', "extension": [1e2, 1e-100]}'
    document = parse_document_text(source)
    assert serialize_document(document) == source
    assert (
        parse_document_text(serialize_document(document)).to_dict()
        == document.to_dict()
    )


def test_invalid_edit_keeps_active_snapshot_unchanged() -> None:
    document = parse_document_data(minimal())
    edited = document.to_dict()
    edited["segments"][0]["text"] = " "
    with pytest.raises(DocumentValidationError):
        document.with_data(edited)
    assert document.revision == 0
    assert document.to_dict() == minimal()


@pytest.mark.parametrize("field", ["text", "speaker", "pause_after_seconds", "speech"])
def test_file_and_memory_errors_match(tmp_path: Path, field: str) -> None:
    data = minimal()
    data["segments"][0][field] = None
    source = json.dumps(data)
    path = tmp_path / "invalid.json"
    path.write_text(source, encoding="utf-8")
    results = []
    for parse in [
        lambda: load_document(path),
        lambda: parse_document_text(source),
        lambda: parse_document_data(data),
    ]:
        with pytest.raises(DocumentValidationError) as caught:
            parse()
        results.append(caught.value.diagnostics)
    assert results[0] == results[1] == results[2]


def test_warning_bound_does_not_drop_extension_data() -> None:
    data = minimal()
    data.update({f"extra_{index}": {"value": index} for index in range(150)})
    document = parse_document_data(data)
    assert len(document.diagnostics) == 101
    assert document.diagnostics[-1].code == "diagnostics_omitted"
    assert document.to_dict() == data
