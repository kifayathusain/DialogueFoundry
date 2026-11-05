"""Typed provider data and cooperative cancellation shared across engines."""

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class VoiceMetadata:
    """A provider-local voice and its known language/model/license metadata."""

    voice_id: str
    display_name: str
    language: str
    model_id: str | None = None
    license_name: str | None = None
    gender: str | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    """Controls and prerequisites actually supported by a provider."""

    online: bool
    audio_formats: tuple[str, ...]
    supports_speed: bool = False
    supports_cancellation: bool = True
    requires_model: bool = False
    requires_download: bool = False
    max_text_characters: int | None = None


@dataclass(frozen=True)
class SynthesisRequest:
    """Text and voice settings for a single native audio segment."""

    text: str
    voice_id: str
    audio_format: str = "mp3"
    language: str | None = None
    speed: float | None = None


@dataclass(frozen=True)
class SynthesisResult:
    """A successfully completed audio segment and its actual native format."""

    output_file: Path
    audio_format: str


class CancellationToken:
    """Thread-safe cancellation signal shared by UI workers and providers."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        """Request cooperative cancellation."""
        self._cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._cancelled.is_set()

    def raise_if_cancelled(self) -> None:
        """Propagate cancellation without treating it as a synthesis failure."""
        if self.is_cancelled:
            raise asyncio.CancelledError

    async def wait(self) -> None:
        """Wait without occupying a worker thread or blocking the event loop."""
        while not self.is_cancelled:
            await asyncio.sleep(0.05)


class TTSProvider(Protocol):
    """UI-independent contract implemented by each synthesis engine."""

    provider_id: str
    display_name: str

    def get_capabilities(self) -> ProviderCapabilities:
        """Describe supported controls without initializing an inference model."""
        ...

    def get_available_voices(self) -> tuple[VoiceMetadata, ...]:
        """Return known voices without silently downloading models."""
        ...

    def validate_configuration(self, request: SynthesisRequest) -> None:
        """Raise an actionable error for unsupported or unavailable settings."""
        ...

    async def synthesize(
        self,
        request: SynthesisRequest,
        output_file: Path,
        cancellation_token: CancellationToken | None = None,
    ) -> SynthesisResult:
        """Write complete native audio or raise, cleaning incomplete resources."""
        ...

    def close(self) -> None:
        """Release retained runtime resources after active work finishes."""
        ...
