"""Structured service acceptance using fake voices and synthetic non-speech PCM."""

import asyncio
import json
import math
import subprocess
import wave
from array import array
from dataclasses import replace
from pathlib import Path

import pytest

from tests.test_generation import OfflineProvider
from ttsapp import generation
from ttsapp.audio_export import ExportSettings, probe_audio
from ttsapp.conversation_document import load_document, parse_document_data
from ttsapp.providers.base import CancellationToken, SynthesisResult
from ttsapp.service import generate_conversation
from ttsapp.text_processing import TextProcessingSettings, normalize_text


class StructuredProvider(OfflineProvider):
    """Use only programmatic PCM, with explicit speed capability."""

    def get_capabilities(self):
        return replace(super().get_capabilities(), supports_speed=True)


def small_document(pause=0.125):
    return parse_document_data(
        {
            "speakers": [{"id": "a", "role": "A", "speech": {"speed": 0.8}}],
            "segments": [
                {
                    "speaker": "a",
                    "text": "First.\n\nSecond. " * 8,
                    "pause_after_seconds": pause,
                },
                {
                    "speaker": "a",
                    "text": "Last: dialogue.",
                    "pause_after_seconds": 0.25,
                    "speech": {"speed": 1.2},
                    "voice_direction": "Private note",
                },
            ],
        }
    )


def invoke(tmp_path, doc, provider, **kwargs):
    return generate_conversation(
        document=doc,
        provider_id=provider.provider_id,
        provider=provider,
        output_dir=tmp_path / "parts",
        final_audio=tmp_path / "final.wav",
        **kwargs,
    )


@pytest.fixture
def captured_export(monkeypatch):
    files = []

    def export(sources, destination, settings, token, **kwargs):
        files.extend(sources)
        destination.write_bytes(b"exported")
        return destination

    monkeypatch.setattr(generation, "export_audio", export)
    return files


def metadata(tmp_path):
    return json.loads(
        next((tmp_path / "parts").glob("job-*/generation.json")).read_text()
    )


def test_sample_exact_pauses_and_only_dialogue(tmp_path, captured_export):
    doc = load_document(Path("examples/structured/tts-sample.json"))
    provider = StructuredProvider()
    progress = []
    asyncio.run(
        invoke(
            tmp_path, doc, provider, on_progress=lambda i, n, line: progress.append(i)
        )
    )
    record = metadata(tmp_path)
    pauses = [item for item in record["timeline"] if item["kind"] == "after_pause"]
    assert len(pauses) == 26
    assert sum(item["seconds"] for item in pauses) == 84
    assert pauses[-1]["seconds"] == 30
    assert progress == list(range(1, 27))
    assert all(item["state"] == "done" for item in record["timeline"])
    after_files = [path for path in captured_export if path.name.startswith("after_")]
    assert captured_export[-1] == after_files[-1]
    assert len(after_files) == sum(
        segment.pause_after_seconds > 0 for segment in doc.segments
    )
    total_frames = 0
    for path in after_files:
        with wave.open(str(path)) as audio:
            total_frames += audio.getnframes()
            assert set(audio.readframes(audio.getnframes())) == {0}
    assert total_frames == 84 * 16000
    for segment in doc.segments:
        assert normalize_text(segment.text) in "".join(
            request.text for request in provider.requests
        )
    assert record["schema_version"] == 2
    assert record["document_id"] == doc.document_id
    assert doc.segments[0].text not in json.dumps(record)


def test_per_chunk_speed_source_span_and_no_paragraph_gaps(tmp_path, captured_export):
    provider = StructuredProvider()
    doc = small_document()
    asyncio.run(
        invoke(tmp_path, doc, provider, voice_assignments={"a": "voice"}, speed=1.5)
    )
    record = metadata(tmp_path)
    assert [item["speed_source"] for item in record["segments"]] == ["role", "segment"]
    assert all(request.voice_id == "voice" for request in provider.requests)
    assert [request.speed for request in provider.requests][-1] == 1.2
    assert all(request.speed == 0.8 for request in provider.requests[:-1])
    assert not any(item["kind"] == "sentence_pause" for item in record["timeline"])
    assert (
        len([path for path in captured_export if path.name.startswith("after_")]) == 2
    )
    for index, segment in enumerate(doc.segments, 1):
        chunks = [item for item in record["chunks"] if item["dialogue_index"] == index]
        assert chunks[0]["source_start"] == 0
        assert chunks[-1]["source_end"] == len(normalize_text(segment.text))
        assert all(
            a["source_end"] == b["source_start"]
            for a, b in zip(chunks, chunks[1:], strict=False)
        )


@pytest.mark.parametrize("pause", [0, 0.000001, 0.12345, 600])
def test_exact_fractional_zero_and_long_pause_frames(tmp_path, captured_export, pause):
    provider = StructuredProvider()
    asyncio.run(invoke(tmp_path, small_document(pause), provider))
    paths = [path for path in captured_export if path.name == "after_00001.wav"]
    assert bool(paths) == (round(16000 * pause) > 0)
    if paths:
        with wave.open(str(paths[0])) as audio:
            assert audio.getnframes() == round(16000 * pause)


def test_sentence_pauses_only_inside_segments(tmp_path, captured_export):
    asyncio.run(
        invoke(
            tmp_path,
            small_document(),
            StructuredProvider(),
            text_settings=TextProcessingSettings(sentence_pause_seconds=0.1),
        )
    )
    timeline = metadata(tmp_path)["timeline"]
    assert sum(item["kind"] == "after_pause" for item in timeline) == 2
    assert sum(item["kind"] == "sentence_pause" for item in timeline) == 15


@pytest.mark.parametrize("invalid", ["mapping", "settings", "source", "late_chunk"])
def test_invalid_requests_have_no_job_or_synthesis(tmp_path, invalid):
    provider = StructuredProvider()
    doc = small_document()
    kwargs = {}
    if invalid == "mapping":
        kwargs["voice_assignments"] = {"a": "invalid"}
    elif invalid == "settings":
        provider.get_capabilities = lambda: replace(
            OfflineProvider().get_capabilities(), supports_speed=False
        )
    elif invalid == "source":
        kwargs["input_text"] = "A: text"
    else:
        data = doc.to_dict()
        data["segments"][-1]["text"] = "REJECT"
        doc = doc.with_data(data)
    with pytest.raises(ValueError):
        asyncio.run(invoke(tmp_path, doc, provider, **kwargs))
    assert not provider.requests
    assert not (tmp_path / "parts").exists()


@pytest.mark.parametrize("cancel", [False, True])
def test_failure_cancel_preserve_final_and_state(tmp_path, captured_export, cancel):
    provider = StructuredProvider()
    if cancel:
        provider.cancel_on_call = 2
    else:
        provider.fail_on_call = 2
    final = tmp_path / "final.wav"
    final.write_bytes(b"previous")
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        asyncio.run(
            invoke(
                tmp_path,
                small_document(),
                provider,
                export_settings=ExportSettings("wav", overwrite=True),
            )
        )
    assert final.read_bytes() == b"previous"
    assert metadata(tmp_path)["state"] == ("cancelled" if cancel else "failed")


def test_identity_changes_with_pause_mapping_speed_and_note(tmp_path, captured_export):
    doc = small_document()
    hashes = []
    for index, change in enumerate(("base", "pause", "speed", "note", "mapping")):
        target = tmp_path / str(index)
        target.mkdir()
        data = doc.to_dict()
        if change == "pause":
            data["segments"][0]["pause_after_seconds"] = 3
        if change == "speed":
            data["segments"][0]["speech"] = {"speed": 1.1}
        if change == "note":
            data["segments"][0]["voice_direction"] = "Other private note"
        provider = StructuredProvider()
        kwargs = {"voice_assignments": {"a": "custom"}} if change == "mapping" else {}
        if kwargs:
            provider.provider_id = "edge"
        asyncio.run(invoke(target, doc.with_data(data), provider, **kwargs))
        hashes.append(metadata(target)["request_sha256"])
    assert len(set(hashes)) == 5


@pytest.mark.parametrize("audio_format", ["wav", "mp3", "m4a"])
@pytest.mark.parametrize("normalize", [False, True])
def test_synthetic_exports_keep_final_silence(tmp_path, audio_format, normalize):
    from ttsapp.audio_files import write_pcm_wav

    class ToneProvider(StructuredProvider):
        async def synthesize(self, request, output_file, cancellation_token=None):
            self.requests.append(request)
            tone = array(
                "h",
                (
                    round(5000 * math.sin(2 * math.pi * 440 * index / 16000))
                    for index in range(16000)
                ),
            )
            write_pcm_wav(
                (tone.tobytes(),),
                output_file,
                16000,
                cancellation_token or CancellationToken(),
            )
            return SynthesisResult(output_file, "wav")

    provider = ToneProvider()
    doc = small_document()
    result = asyncio.run(
        generate_conversation(
            document=doc,
            provider=provider,
            provider_id=provider.provider_id,
            output_dir=tmp_path / "parts",
            final_audio=tmp_path / f"final.{audio_format}",
            export_settings=ExportSettings(audio_format, normalize=normalize),
        )
    )
    info = probe_audio(result, CancellationToken())
    expected = len(provider.requests) + 0.375
    assert abs(info.duration_seconds - expected) < 0.12
    decoded = tmp_path / "decoded.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(result),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(decoded),
        ],
        check=True,
        capture_output=True,
    )
    with wave.open(str(decoded)) as audio:
        audio.setpos(max(0, audio.getnframes() - round(audio.getframerate() * 0.1)))
        samples = audio.readframes(round(audio.getframerate() * 0.05))
        assert not any(samples)


def test_online_native_mp3_decoded_once_per_chunk(tmp_path):
    seed = tmp_path / "seed.wav"
    from ttsapp.audio_files import write_pcm_wav

    write_pcm_wav((b"\x10\x00" * 1600,), seed, 16000, CancellationToken())
    mp3 = tmp_path / "seed.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(seed), str(mp3)],
        check=True,
        capture_output=True,
    )

    class Online(StructuredProvider):
        def get_capabilities(self):
            return replace(
                super().get_capabilities(), online=True, audio_formats=("mp3",)
            )

        async def synthesize(self, request, output_file, cancellation_token=None):
            self.requests.append(request)
            output_file.write_bytes(mp3.read_bytes())
            return SynthesisResult(output_file, "mp3")

    provider = Online()
    asyncio.run(invoke(tmp_path, small_document(), provider))
    assert len(list((tmp_path / "parts").glob("job-*/chunk_*.mp3"))) == len(
        provider.requests
    )
    assert len(list((tmp_path / "parts").glob("job-*/chunk_*.wav"))) == len(
        provider.requests
    )
    assert (
        probe_audio(tmp_path / "final.wav", CancellationToken()).duration_seconds
        > 0.375
    )


@pytest.mark.parametrize("stage", ["silence", "decode", "export"])
def test_cancellation_during_blocking_stage_waits_for_cleanup(
    tmp_path, monkeypatch, stage
):
    import threading
    import time

    started = threading.Event()
    cleaned = threading.Event()

    def blocked(*args, **kwargs):
        token = args[-1]
        started.set()
        try:
            while not token.is_cancelled:
                time.sleep(0.005)
            token.raise_if_cancelled()
        finally:
            cleaned.set()

    provider = StructuredProvider()
    if stage == "silence":
        monkeypatch.setattr(generation, "write_silence", blocked)
    elif stage == "export":
        monkeypatch.setattr(generation, "export_audio", blocked)
    else:
        provider.get_capabilities = lambda: replace(
            StructuredProvider().get_capabilities(), online=True, audio_formats=("mp3",)
        )

        async def native(request, output, token):
            output.write_bytes(b"fake compressed audio")
            return SynthesisResult(output, "mp3")

        provider.synthesize = native
        monkeypatch.setattr(generation.audio_combiner, "decode_to_wav", blocked)

    final = tmp_path / "final.wav"
    final.write_bytes(b"previous")

    async def exercise():
        task = asyncio.create_task(
            invoke(
                tmp_path,
                small_document(),
                provider,
                export_settings=ExportSettings("wav", overwrite=True),
            )
        )
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        assert cleaned.is_set()

    asyncio.run(exercise())
    assert final.read_bytes() == b"previous"
    assert metadata(tmp_path)["state"] == "cancelled"
    assert not list((tmp_path / "parts").rglob(".metadata-*"))


@pytest.mark.parametrize("permanent", [False, True])
def test_metadata_windows_sharing_failure_is_bounded_and_preserves_output(
    tmp_path, captured_export, monkeypatch, permanent
):
    original = generation.os.replace
    attempts = []

    def publish(source, destination):
        if destination.name == "generation.json" and (permanent or len(attempts) < 2):
            attempts.append(True)
            error = PermissionError("Injected Windows sharing violation")
            error.winerror = 32
            raise error
        return original(source, destination)

    monkeypatch.setattr(generation.os, "replace", publish)
    monkeypatch.setattr(generation.time, "sleep", lambda seconds: None)
    if permanent:
        with pytest.raises(PermissionError):
            asyncio.run(invoke(tmp_path, small_document(), StructuredProvider()))
        assert len(attempts) <= 4
        assert not (tmp_path / "final.wav").exists()
        assert not list((tmp_path / "parts").rglob(".metadata-*"))
    else:
        asyncio.run(invoke(tmp_path, small_document(), StructuredProvider()))
        assert (tmp_path / "final.wav").read_bytes() == b"exported"
        assert metadata(tmp_path)["state"] == "done"
        assert len(attempts) == 2
