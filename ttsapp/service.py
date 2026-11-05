"""Application/service layer orchestrating parsing, synthesis and combining.

This is the layer the CLI and desktop UI use instead of talking to the
TTS/FFmpeg adapters directly.
"""

from collections.abc import Callable
from functools import partial
from pathlib import Path

from . import audio_combiner, tts_engine
from .audio_effects import AudioTreatment
from .audio_export import (
    ExportProgressCallback,
    ExportSettings,
    export_audio,
    validate_export_target,
)
from .config import DEFAULT_FINAL_AUDIO, DEFAULT_INPUT_FILE, DEFAULT_OUTPUT_DIR, VOICES
from .conversation_document import ConversationDocument, DocumentValidationError
from .generation import ChunkProgressCallback, generate_processed_conversation
from .parser import ConversationLine, parse_conversation, parse_conversation_text
from .provider_manager import ProviderChoice
from .providers.base import CancellationToken, SynthesisRequest, TTSProvider
from .providers.registry import create_default_registry
from .speaker_mapping import resolve_document
from .text_processing import TextProcessingSettings
from .workers import run_blocking_work

ProgressCallback = Callable[[int, int, ConversationLine], None] | None


async def generate_conversation(
    input_file: Path = DEFAULT_INPUT_FILE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    final_audio: Path = DEFAULT_FINAL_AUDIO,
    voices: dict[str, str] = VOICES,
    on_progress: ProgressCallback = None,
    input_text: str | None = None,
    *,
    provider_id: str = "edge",
    provider: TTSProvider | None = None,
    cancellation_token: CancellationToken | None = None,
    text_settings: TextProcessingSettings | None = None,
    on_chunk_progress: ChunkProgressCallback | None = None,
    speed: float | None = None,
    export_settings: ExportSettings | None = None,
    on_export_progress: ExportProgressCallback | None = None,
    document: ConversationDocument | None = None,
    voice_assignments: dict[str, str] | None = None,
    segment_treatments: dict[int, AudioTreatment] | None = None,
    speaker_providers: dict[str, TTSProvider] | None = None,
) -> Path:
    """Run the full pipeline: parse -> synthesize each line -> combine audio.

    If ``input_text`` is provided (e.g. from the desktop UI's text box), it is
    parsed directly instead of reading ``input_file`` from disk. Otherwise the
    script is read from ``input_file``, preserving the original CLI behavior.

    Returns the path to the final combined audio file.
    """

    if provider is not None and provider_id != provider.provider_id:
        raise ValueError("Provider ID must match the injected provider.")
    selected_provider = provider or create_default_registry().get(provider_id)
    if cancellation_token is not None:
        cancellation_token.raise_if_cancelled()
    if export_settings is not None:
        validate_export_target(final_audio, export_settings)

    resolved_segments = None
    if speaker_providers is not None and document is None:
        raise ValueError("Speaker providers require a structured document.")
    if segment_treatments is not None and document is None:
        raise ValueError("Segment treatments require a structured document.")
    if document is not None:
        if input_text is not None or input_file != DEFAULT_INPUT_FILE:
            raise ValueError(
                "Choose a document or an explicit text/file source, not both."
            )
        capabilities = selected_provider.get_capabilities()
        speaker_choices = {}
        for speaker, engine in (speaker_providers or {}).items():
            if speaker not in {s.id for s in document.speakers}:
                raise ValueError(f"Unknown speaker provider assignment: {speaker}.")
            controls = engine.get_capabilities()
            speaker_choices[speaker] = ProviderChoice(
                engine.provider_id,
                engine.display_name,
                engine.get_available_voices(),
                controls.online,
                controls.supports_speed,
            )
        preflight = resolve_document(
            document,
            ProviderChoice(
                provider_id,
                selected_provider.display_name,
                selected_provider.get_available_voices(),
                capabilities.online,
                capabilities.supports_speed,
            ),
            current=voice_assignments,
            job_speed=speed,
            speaker_choices=speaker_choices,
        )
        if preflight.errors:
            raise DocumentValidationError(preflight.errors)
        resolved_segments = preflight.segments
        lines = [
            ConversationLine(item.index, item.speaker_id, item.text, item.voice_id)
            for item in resolved_segments
        ]
        if export_settings is None:
            export_settings = ExportSettings(
                audio_format=final_audio.suffix.lstrip(".").lower()
            )
        validate_export_target(final_audio, export_settings)
    elif input_text is not None:
        lines = parse_conversation_text(input_text, voices)
    else:
        lines = parse_conversation(input_file, voices)

    if not lines:
        raise ValueError("Conversation script must contain at least one dialogue line.")

    capabilities = selected_provider.get_capabilities()
    if "mp3" in capabilities.audio_formats:
        native_format = "mp3"
    elif "wav" in capabilities.audio_formats:
        native_format = "wav"
    else:
        raise ValueError("This pipeline requires native MP3 or WAV segments.")
    if document is not None or text_settings is not None or not capabilities.online:
        return await generate_processed_conversation(
            lines,
            selected_provider,
            native_format=native_format,
            output_dir=output_dir,
            final_audio=final_audio,
            settings=text_settings or TextProcessingSettings(),
            cancellation_token=cancellation_token,
            on_progress=on_progress,
            on_chunk_progress=on_chunk_progress,
            speed=speed,
            export_settings=export_settings,
            on_export_progress=on_export_progress,
            resolved_segments=resolved_segments,
            document_hash=document.content_hash if document is not None else None,
            segment_treatments=segment_treatments,
            segment_providers={
                segment.index: (speaker_providers or {}).get(
                    segment.speaker_id, selected_provider
                )
                for segment in resolved_segments or ()
            }
            if speaker_providers is not None
            else None,
        )
    for line in lines:
        selected_provider.validate_configuration(
            SynthesisRequest(
                line.text, line.voice, audio_format=native_format, speed=speed
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    audio_files: list[Path] = []
    total = len(lines)

    for line in lines:
        output_file = tts_engine.line_output_path(output_dir, line.index)
        if native_format == "wav":
            output_file = output_file.with_suffix(".wav")
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()
        await selected_provider.synthesize(
            SynthesisRequest(
                line.text, line.voice, audio_format=native_format, speed=speed
            ),
            output_file,
            cancellation_token,
        )
        audio_files.append(output_file)

        if on_progress is not None:
            on_progress(line.index, total, line)

    if cancellation_token is not None:
        cancellation_token.raise_if_cancelled()
    if export_settings is not None:
        return await run_blocking_work(
            partial(
                export_audio,
                audio_files,
                final_audio,
                export_settings,
                on_progress=on_export_progress,
            ),
            cancellation_token,
        )
    if native_format == "wav":
        return audio_combiner.combine_audio(
            audio_files,
            output_dir,
            final_audio,
            source_format="wav",
            cancellation_token=cancellation_token,
        )
    if cancellation_token is not None:
        return audio_combiner.combine_audio(
            audio_files, output_dir, final_audio, cancellation_token=cancellation_token
        )
    return audio_combiner.combine_audio(audio_files, output_dir, final_audio)
