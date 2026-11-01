"""Approved deterministic speech treatments shared by all synthesis providers."""

import math
import wave
from dataclasses import dataclass
from pathlib import Path

from .audio_process import run_audio_process
from .providers.base import CancellationToken


@dataclass(frozen=True)
class AudioTreatment:
    """Bounded controls, never arbitrary FFmpeg expressions or external assets."""

    telephone: bool = False
    room_level: float = 0
    cue: str | None = None

    def __post_init__(self) -> None:
        if type(self.telephone) is not bool:
            raise ValueError("Telephone treatment must be a boolean.")
        if (
            isinstance(self.room_level, bool)
            or not isinstance(self.room_level, (int, float))
            or not math.isfinite(self.room_level)
            or not 0 <= self.room_level <= 0.015
        ):
            raise ValueError("Room level must be between 0 and 0.015.")
        if self.cue not in {None, "paper", "chair"}:
            raise ValueError("Unknown locally generated cue.")


def apply_treatment(
    source: Path, output: Path, treatment: AudioTreatment, token: CancellationToken
) -> Path:
    """Process one speech chunk; scripted pauses never pass through effects."""
    token.raise_if_cancelled()
    if not treatment.telephone and not treatment.room_level and not treatment.cue:
        return source
    with wave.open(str(source)) as audio:
        seconds = audio.getnframes() / audio.getframerate()
        rate = audio.getframerate()
        channels = audio.getnchannels()
    filters = []
    speech = "anull"
    if treatment.telephone:
        speech = "highpass=f=300,lowpass=f=3400"
    filters.append(f"[0:a]{speech}[speech]")
    streams = ["[speech]"]
    if treatment.room_level:
        filters.append(
            f"anoisesrc=color=brown:amplitude={treatment.room_level}:"
            f"sample_rate={rate}:duration={seconds}:seed=42[room]"
        )
        streams.append("[room]")
    if treatment.cue:
        color = "pink" if treatment.cue == "paper" else "brown"
        duration = min(seconds, 0.22)
        filters.append(
            f"anoisesrc=color={color}:amplitude=0.012:sample_rate={rate}:"
            f"duration={duration}:seed=17,afade=t=out:st=0:d={duration}[cue]"
        )
        streams.append("[cue]")
    filters.append(
        "".join(streams) + f"amix=inputs={len(streams)}:duration=first:normalize=0,"
        "alimiter=limit=0.95:level=0:latency=1[out]"
    )
    try:
        run_audio_process(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[out]",
                "-ar",
                str(rate),
                "-ac",
                str(channels),
                "-c:a",
                "pcm_s16le",
                str(output),
            ],
            token,
        )
        return output
    except BaseException:
        output.unlink(missing_ok=True)
        raise
