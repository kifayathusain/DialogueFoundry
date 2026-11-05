"""CLI shared-service parity and cleanup, entirely behind fake boundaries."""

import asyncio
import json
from pathlib import Path

import pytest

from tests.test_structured_gui import FakeSource
from ttsapp import cli
from ttsapp.conversation_document import load_document
from ttsapp.speaker_mapping import resolve_document


def arguments(tmp_path, *extra):
    return cli.argument_parser().parse_args(
        [
            "--input",
            "examples/structured/tts-sample.json",
            "--output",
            str(tmp_path / "result.wav"),
            *extra,
        ]
    )


def test_json_cli_uses_shared_snapshot_and_resolver(tmp_path, monkeypatch):
    source = FakeSource(tmp_path / "models")
    calls = []

    async def generate(**kwargs):
        calls.append(kwargs)
        return kwargs["final_audio"]

    monkeypatch.setattr(cli, "generate_conversation", generate)
    args = arguments(tmp_path)
    asyncio.run(cli.generate_from_arguments(args, providers=source))
    assert source.closed
    call = calls[0]
    assert call["provider_id"] == "edge"
    assert (
        call["document"].to_dict()
        == load_document(Path("examples/structured/tts-sample.json")).to_dict()
    )
    assert not call["export_settings"].overwrite
    choice = source.list_choices()[0]
    a = resolve_document(call["document"], choice, current=call["voice_assignments"])
    b = resolve_document(
        load_document(Path("examples/structured/tts-sample.json")), choice
    )
    assert [(s.voice_id, s.pause_after_seconds) for s in a.segments] == [
        (s.voice_id, s.pause_after_seconds) for s in b.segments
    ]


@pytest.mark.parametrize("invalid", ["provider", "speaker", "local_voice", "malformed"])
def test_invalid_cli_map_fails_before_provider_get(tmp_path, monkeypatch, invalid):
    doc = load_document(Path("examples/structured/tts-sample.json"))
    mapping = {
        "schema_version": 1,
        "provider_id": "edge",
        "voices": {doc.speakers[0].id: "custom"},
    }
    extras = []
    if invalid == "provider":
        extras = ["--provider", "piper"]
    elif invalid == "speaker":
        mapping["voices"]["unknown"] = "custom"
    elif invalid == "local_voice":
        mapping["provider_id"] = "piper"
    target = tmp_path / "voices.json"
    target.write_text(
        "{" if invalid == "malformed" else json.dumps(mapping), encoding="utf-8"
    )
    source = FakeSource(tmp_path / "models")

    def forbidden(*args):
        raise AssertionError("Provider should not be acquired")

    monkeypatch.setattr(source, "get", forbidden)
    with pytest.raises(ValueError):
        asyncio.run(
            cli.generate_from_arguments(
                arguments(tmp_path, "--voice-map", str(target), *extras),
                providers=source,
            )
        )
    assert source.closed


@pytest.mark.parametrize("cancel", [False, True])
def test_cli_failure_and_interrupt_close_sessions(tmp_path, monkeypatch, cancel):
    source = FakeSource(tmp_path / "models")

    async def fail(**kwargs):
        raise asyncio.CancelledError if cancel else RuntimeError("Injected failure")

    monkeypatch.setattr(cli, "generate_conversation", fail)
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        asyncio.run(cli.generate_from_arguments(arguments(tmp_path), providers=source))
    assert source.closed


def test_run_cli_error_is_nonzero_without_traceback(tmp_path, monkeypatch, capsys):
    async def fail(*args, **kwargs):
        raise ValueError("Correct the voice mapping.")

    monkeypatch.setattr(cli, "generate_from_arguments", fail)
    assert cli.run_cli(["--input", "examples/structured/tts-sample.json"]) == 1
    error = capsys.readouterr().err
    assert "Correct the voice mapping" in error
    assert "Traceback" not in error


def test_explicit_json_cli_refuses_overwrite_and_closes_session(tmp_path):
    source = FakeSource(tmp_path / "models")
    args = arguments(tmp_path)
    args.output.write_bytes(b"previous")
    with pytest.raises(FileExistsError):
        asyncio.run(cli.generate_from_arguments(args, providers=source))
    assert source.closed
    assert not source.fake.requests
    assert args.output.read_bytes() == b"previous"


def test_full_stable_piper_id_survives_cli_boundary(tmp_path, monkeypatch):
    doc = load_document(Path("examples/structured/tts-sample.json"))
    stable_id = "en_GB-vctk-medium:speaker_108"
    mapping = tmp_path / "piper.json"
    mapping.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider_id": "piper",
                "voices": {speaker.id: stable_id for speaker in doc.speakers},
            }
        ),
        encoding="utf-8",
    )
    captured = []

    async def generate(**kwargs):
        captured.append(kwargs)
        return kwargs["final_audio"]

    monkeypatch.setattr(cli, "generate_conversation", generate)
    source = FakeSource(tmp_path / "models")
    asyncio.run(
        cli.generate_from_arguments(
            arguments(tmp_path, "--voice-map", str(mapping)),
            providers=source,
        )
    )
    assert set(captured[0]["voice_assignments"].values()) == {stable_id}
    assert captured[0]["provider_id"] == "piper"
    assert source.closed
