"""FFmpeg adapter used to concatenate generated audio segments."""

import os
import subprocess
import tempfile
import wave
from pathlib import Path

from .providers.base import CancellationToken


class FFmpegNotFoundError(RuntimeError):
    """Raised when the ``ffmpeg`` executable is not available on PATH."""


class FFmpegExecutionError(RuntimeError):
    """Raised when FFmpeg cannot combine the generated audio segments."""


def _run_ffmpeg(command: list[str], action: str) -> None:
    """Run safe argument-list processing and preserve actionable adapter errors."""
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise FFmpegNotFoundError(
            "ffmpeg executable was not found on PATH. Install FFmpeg and "
            "ensure 'ffmpeg' is runnable from the command line."
        ) from error
    except subprocess.CalledProcessError as error:
        details = (error.stderr or "").strip()
        message = f"FFmpeg could not {action} (exit code {error.returncode})."
        if details:
            message = f"{message} {details}"
        raise FFmpegExecutionError(message) from error


def decode_to_wav(
    source_file: Path,
    output_file: Path,
    cancellation_token: CancellationToken,
    *,
    sample_rate: int | None = None,
) -> None:
    """Decode compressed native audio once to a lossless mono PCM intermediate."""
    from .audio_process import run_audio_process

    cancellation_token.raise_if_cancelled()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{output_file.stem}.", suffix=".wav", dir=output_file.parent
    )
    os.close(descriptor)
    temporary = Path(name)
    try:
        run_audio_process(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_file),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                *(["-ar", str(sample_rate)] if sample_rate is not None else []),
                str(temporary),
            ],
            cancellation_token,
        )
        try:
            with wave.open(str(temporary), "rb") as audio:
                if audio.getnframes() == 0:
                    raise FFmpegExecutionError("FFmpeg produced empty PCM audio.")
        except (wave.Error, EOFError) as error:
            raise FFmpegExecutionError(
                "FFmpeg did not produce valid PCM audio."
            ) from error
        cancellation_token.raise_if_cancelled()
        os.replace(temporary, output_file)
    finally:
        temporary.unlink(missing_ok=True)


def _concat_path(audio_file: Path) -> str:
    """Return a concat-demuxer-safe, absolute path."""

    path = audio_file.resolve().as_posix()
    return path.replace("'", "'\\''")


def write_concat_file(audio_files: list[Path], concat_file: Path) -> None:
    """Write an FFmpeg "concat demuxer" list file for ``audio_files``."""

    with open(concat_file, "w", encoding="utf-8", newline="\n") as file:
        for audio_file in audio_files:
            file.write(f"file '{_concat_path(audio_file)}'\n")


def _output_codec(
    audio_files: list[Path], final_audio: Path, source_format: str | None
) -> str:
    """Keep legacy stream copy or explicitly encode compatible native WAV input."""
    if source_format is None:
        return "copy"
    if source_format != "wav":
        raise ValueError("Explicit source format must be WAV.")
    if final_audio.suffix.lower() == ".mp3":
        codec = "libmp3lame"
    elif final_audio.suffix.lower() == ".wav":
        codec = "pcm_s16le"
    else:
        raise ValueError("Native WAV export currently supports MP3 or WAV output.")
    previous_format = None
    for audio_file in audio_files:
        with wave.open(str(audio_file), "rb") as source:
            audio_format = (
                source.getnchannels(),
                source.getsampwidth(),
                source.getframerate(),
            )
            if source.getnframes() == 0:
                raise ValueError("Cannot export an empty WAV segment.")
        if previous_format is not None and audio_format != previous_format:
            raise ValueError(
                "WAV segments must have matching sample rates and channels."
            )
        previous_format = audio_format
    return codec


def combine_audio(
    audio_files: list[Path],
    output_dir: Path,
    final_audio: Path,
    *,
    source_format: str | None = None,
    cancellation_token: CancellationToken | None = None,
) -> Path:
    """Concatenate ``audio_files`` in order, preserving any prior output on failure."""

    if not audio_files:
        raise ValueError("At least one audio segment is required for combination.")
    if cancellation_token is not None:
        cancellation_token.raise_if_cancelled()
    codec = _output_codec(audio_files, final_audio, source_format)

    output_dir.mkdir(parents=True, exist_ok=True)
    final_audio.parent.mkdir(parents=True, exist_ok=True)

    concat_descriptor, concat_name = tempfile.mkstemp(
        prefix=".concat-", suffix=".txt", dir=str(output_dir)
    )
    concat_file = Path(concat_name)
    temporary_audio = None

    try:
        os.close(concat_descriptor)

        output_descriptor, output_name = tempfile.mkstemp(
            prefix=f".{final_audio.stem}.",
            suffix=final_audio.suffix or ".mp3",
            dir=str(final_audio.parent),
        )
        temporary_audio = Path(output_name)
        os.close(output_descriptor)

        write_concat_file(audio_files, concat_file)

        _run_ffmpeg(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                codec,
                str(temporary_audio),
            ],
            "combine the audio segments",
        )

        if not temporary_audio.is_file() or temporary_audio.stat().st_size == 0:
            raise FFmpegExecutionError(
                "FFmpeg completed without producing a non-empty audio file."
            )

        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()
        os.replace(temporary_audio, final_audio)
        return final_audio
    finally:
        concat_file.unlink(missing_ok=True)
        if temporary_audio is not None:
            temporary_audio.unlink(missing_ok=True)
