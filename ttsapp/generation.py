"""Chunk orchestration, lossless pauses, and auditable generation metadata."""

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import time
import uuid
import wave
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Literal

from . import audio_combiner
from .audio_export import (
    ExportProgressCallback,
    ExportSettings,
    export_audio,
    validate_export_target,
)
from .audio_files import write_silence
from .parser import ConversationLine
from .providers.base import CancellationToken, SynthesisRequest, TTSProvider
from .speaker_mapping import ResolvedSegment
from .text_processing import (
    SpeechChunk,
    TextProcessingSettings,
    chunk_conversation,
    normalize_text,
)
from .workers import run_blocking_work

logger = logging.getLogger(__name__)
ChunkProgressCallback = Callable[[int, int, SpeechChunk], None]
LineProgressCallback = Callable[[int, int, ConversationLine], None]


@dataclass
class ChunkRecord:
    """A normalized source span and output identity, without recording private text."""

    index: int
    dialogue_index: int
    voice_id: str
    source_start: int
    source_end: int
    text_sha256: str
    output_filename: str
    state: Literal["pending", "running", "done", "failed", "cancelled"] = "pending"
    audio_sha256: str | None = None
    speed: float | None = None


@dataclass
class TimelineItem:
    """Ordered planned speech/silence with materialization state."""

    kind: str
    segment_index: int
    chunk_index: int
    seconds: float = 0
    state: str = "pending"


@dataclass(frozen=True)
class ResolvedSegmentMetadata:
    """Public effective settings without private dialogue or note bodies."""

    index: int
    speaker_id: str
    voice_id: str
    speed: float | None
    speed_source: str
    pause_after_seconds: float
    direction_status: str


@dataclass
class GenerationRecord:
    """Versioned evidence for future safe resumption; no implicit audio reuse."""

    schema_version: int
    provider_id: str
    request_sha256: str
    settings: TextProcessingSettings
    speed: float | None
    export_settings: ExportSettings | None
    chunks: list[ChunkRecord]
    state: Literal["running", "done", "failed", "cancelled"] = "running"
    document_id: str | None = None
    document_revision: int | None = None
    timeline: list[TimelineItem] | None = None
    segments: list[ResolvedSegmentMetadata] | None = None
    assignment_sha256: str | None = None


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _write_record(record: GenerationRecord, destination: Path) -> None:
    """Atomically update job state, so interruptions cannot leave partial JSON."""
    descriptor, name = tempfile.mkstemp(prefix=".metadata-", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        temporary.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
        for delay in (0.01, 0.03, 0.1, None):
            try:
                os.replace(temporary, destination)
                break
            except PermissionError as error:
                # Windows scanners can briefly hold the previous metadata open.
                # Permanent permissions and exhausted retries remain failures.
                if error.winerror not in {5, 32, 33} or delay is None:
                    raise
                time.sleep(delay)
    finally:
        temporary.unlink(missing_ok=True)


def _initial_record(
    lines: list[ConversationLine],
    provider: TTSProvider,
    settings: TextProcessingSettings,
    chunks: tuple[SpeechChunk, ...],
    speed: float | None,
    export_settings: ExportSettings | None,
) -> GenerationRecord:
    request_identity = {
        "provider": provider.provider_id,
        "voices": [asdict(voice) for voice in provider.get_available_voices()],
        "settings": asdict(settings),
        "speed": speed,
        "export": asdict(export_settings) if export_settings is not None else None,
        "source": [
            {
                "original_sha256": _text_digest(line.text),
                "normalized_sha256": _text_digest(normalize_text(line.text)),
                "voice": line.voice,
                "paragraph_break_before": line.paragraph_break_before,
            }
            for line in lines
        ],
    }
    return GenerationRecord(
        schema_version=1,
        provider_id=provider.provider_id,
        request_sha256=_text_digest(json.dumps(request_identity, sort_keys=True)),
        settings=settings,
        speed=speed,
        export_settings=export_settings,
        chunks=[
            ChunkRecord(
                index=chunk.index,
                dialogue_index=chunk.dialogue_index,
                voice_id=chunk.voice_id,
                source_start=chunk.source_start,
                source_end=chunk.source_end,
                text_sha256=_text_digest(chunk.text),
                output_filename=f"chunk_{chunk.index:05d}.wav",
            )
            for chunk in chunks
        ],
    )


async def _synthesize_chunk(
    chunk: SpeechChunk,
    provider: TTSProvider,
    native_format: str,
    output: Path,
    token: CancellationToken,
    speed: float | None,
) -> None:
    native_output = output.with_suffix(f".{native_format}")
    result = await provider.synthesize(
        SynthesisRequest(
            chunk.text, chunk.voice_id, audio_format=native_format, speed=speed
        ),
        native_output,
        token,
    )
    if result.output_file != native_output or result.audio_format != native_format:
        raise ValueError("Provider result did not match the requested native output.")
    if native_format == "mp3":
        await run_blocking_work(
            partial(audio_combiner.decode_to_wav, native_output, output), token
        )
    with wave.open(str(output), "rb") as audio:
        if audio.getnframes() == 0:
            raise ValueError("Provider produced an empty audio chunk.")


async def generate_processed_conversation(
    lines: list[ConversationLine],
    provider: TTSProvider,
    *,
    native_format: str,
    output_dir: Path,
    final_audio: Path,
    settings: TextProcessingSettings,
    cancellation_token: CancellationToken | None,
    on_progress: LineProgressCallback | None,
    on_chunk_progress: ChunkProgressCallback | None,
    speed: float | None = None,
    export_settings: ExportSettings | None = None,
    on_export_progress: ExportProgressCallback | None = None,
    resolved_segments: tuple[ResolvedSegment, ...] | None = None,
    document_hash: str | None = None,
) -> Path:
    """Generate an isolated, tracked job with complete ordered lossless chunks."""
    token = cancellation_token or CancellationToken()
    token.raise_if_cancelled()
    chunks = chunk_conversation(
        lines, settings, provider.get_capabilities().max_text_characters
    )
    if export_settings is not None:
        validate_export_target(final_audio, export_settings)
    elif final_audio.suffix.lower() not in {".mp3", ".wav"}:
        raise ValueError("Processed audio currently supports MP3 or WAV output.")
    effective_speeds = {item.index: item.speed for item in resolved_segments or ()}
    for chunk in chunks:
        provider.validate_configuration(
            SynthesisRequest(
                chunk.text,
                chunk.voice_id,
                audio_format=native_format,
                speed=effective_speeds.get(chunk.dialogue_index, speed),
            )
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    job_directory = output_dir / f"job-{uuid.uuid4().hex}"
    job_directory.mkdir()
    record = _initial_record(lines, provider, settings, chunks, speed, export_settings)
    if resolved_segments is not None:
        record.schema_version = 2
        record.document_id = resolved_segments[0].document_id
        record.document_revision = resolved_segments[0].revision
        record.segments = [
            ResolvedSegmentMetadata(
                item.index,
                item.speaker_id,
                item.voice_id,
                item.speed,
                item.speed_source,
                item.pause_after_seconds,
                item.direction_status,
            )
            for item in resolved_segments
        ]
        record.assignment_sha256 = _text_digest(
            json.dumps(
                {item.speaker_id: item.voice_id for item in resolved_segments},
                sort_keys=True,
            )
        )
        record.request_sha256 = _text_digest(
            json.dumps(
                {
                    "base": record.request_sha256,
                    "document_hash": document_hash,
                    "segments": [asdict(item) for item in record.segments],
                },
                sort_keys=True,
            )
        )
        record.timeline = []
        for offset, chunk in enumerate(chunks):
            record.chunks[offset].speed = effective_speeds[chunk.dialogue_index]
            if chunk.pause_before_seconds:
                record.timeline.append(
                    TimelineItem(
                        "sentence_pause",
                        chunk.dialogue_index,
                        chunk.index,
                        chunk.pause_before_seconds,
                    )
                )
            record.timeline.append(
                TimelineItem("speech", chunk.dialogue_index, chunk.index)
            )
            if (
                offset + 1 == len(chunks)
                or chunks[offset + 1].dialogue_index != chunk.dialogue_index
            ):
                record.timeline.append(
                    TimelineItem(
                        "after_pause",
                        chunk.dialogue_index,
                        chunk.index,
                        resolved_segments[chunk.dialogue_index - 1].pause_after_seconds,
                    )
                )
    metadata_file = job_directory / "generation.json"
    _write_record(record, metadata_file)
    audio_files: list[Path] = []
    try:
        for offset, chunk in enumerate(chunks):
            token.raise_if_cancelled()
            item = record.chunks[offset]
            item.state = "running"
            _write_record(record, metadata_file)
            output = job_directory / item.output_filename
            await _synthesize_chunk(
                chunk,
                provider,
                native_format,
                output,
                token,
                effective_speeds.get(chunk.dialogue_index, speed),
            )
            if chunk.pause_before_seconds > 0 and audio_files:
                with wave.open(str(output)) as audio:
                    sample_rate = audio.getframerate()
                silence = job_directory / f"pause_{chunk.index:05d}.wav"
                await run_blocking_work(
                    partial(
                        write_silence, silence, sample_rate, chunk.pause_before_seconds
                    ),
                    token,
                )
                audio_files.append(silence)
            audio_files.append(output)
            item.audio_sha256 = _file_digest(output)
            item.state = "done"
            _write_record(record, metadata_file)
            if on_chunk_progress is not None:
                on_chunk_progress(chunk.index, len(chunks), chunk)
            last_for_line = (
                offset + 1 == len(chunks)
                or chunks[offset + 1].dialogue_index != chunk.dialogue_index
            )
            if resolved_segments is not None:
                for planned in record.timeline or ():
                    if (
                        planned.chunk_index == chunk.index
                        and planned.kind != "after_pause"
                    ):
                        planned.state = "done"
                if last_for_line:
                    seconds = resolved_segments[
                        chunk.dialogue_index - 1
                    ].pause_after_seconds
                    with wave.open(str(output)) as audio:
                        rate = audio.getframerate()
                    if round(rate * seconds) > 0:
                        silence = (
                            job_directory / f"after_{chunk.dialogue_index:05d}.wav"
                        )
                        await run_blocking_work(
                            partial(write_silence, silence, rate, seconds), token
                        )
                        audio_files.append(silence)
                for planned in record.timeline or ():
                    if planned.chunk_index == chunk.index:
                        planned.state = "done"
                _write_record(record, metadata_file)
            if last_for_line and on_progress is not None:
                line = lines[chunk.dialogue_index - 1]
                on_progress(line.index, len(lines), line)
        token.raise_if_cancelled()
        if export_settings is not None:
            result = await run_blocking_work(
                partial(
                    export_audio,
                    audio_files,
                    final_audio,
                    export_settings,
                    on_progress=on_export_progress,
                ),
                token,
            )
        else:
            result = audio_combiner.combine_audio(
                audio_files,
                job_directory,
                final_audio,
                source_format="wav",
                cancellation_token=token,
            )
        record.state = "done"
        try:
            _write_record(record, metadata_file)
        except OSError as error:
            logger.warning(
                "Audio completed but final metadata update failed: %s", error
            )
        return result
    except asyncio.CancelledError:
        token.cancel()
        record.state = "cancelled"
        for planned in record.timeline or ():
            if planned.state != "done":
                planned.state = "cancelled"
        for item in record.chunks:
            if item.state == "running":
                item.state = "cancelled"
        raise
    except Exception:
        # A provider failure must remain visible while the job records its state.
        record.state = "failed"
        for planned in record.timeline or ():
            if planned.state != "done":
                planned.state = "failed"
        for item in record.chunks:
            if item.state == "running":
                item.state = "failed"
        raise
    finally:
        if record.state != "done":
            try:
                _write_record(record, metadata_file)
            except OSError as error:
                logger.warning(
                    "Could not persist interrupted generation state: %s", error
                )
