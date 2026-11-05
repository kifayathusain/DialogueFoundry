"""Desktop provider selection and session lifecycle without any widget dependency."""

import hashlib
import json
import threading
from dataclasses import asdict, dataclass

from .models.assets import ModelValidationError
from .models.catalog import default_catalog, default_manifest
from .models.kokoro_catalog import kokoro_v1_model
from .models.manager import InstallationState, ModelManager
from .models.piper_catalog import english_models
from .providers.base import TTSProvider, VoiceMetadata
from .providers.edge import EdgeTTSProvider
from .providers.kokoro import KokoroTTSProvider
from .providers.piper import PiperModel, PiperTTSProvider


@dataclass(frozen=True)
class ProviderChoice:
    """Fast provider/voice metadata suitable for presenting on the UI thread."""

    provider_id: str
    display_name: str
    voices: tuple[VoiceMetadata, ...]
    online: bool
    supports_speed: bool
    model_id: str | None = None


class ProviderManager:
    """Keep one desktop session, or retain CLI cast sessions until close."""

    def __init__(
        self, models: ModelManager | None = None, *, retain_sessions: bool = False
    ) -> None:
        self.models = models if models is not None else ModelManager()
        self._selected: TTSProvider | None = None
        self._lock = threading.Lock()
        self._retain_sessions = retain_sessions
        self._sessions: dict[str, TTSProvider] = {}

    def list_choices(self) -> tuple[ProviderChoice, ...]:
        """Describe choices without opening model files or importing optional runtimes."""
        edge = EdgeTTSProvider()
        kokoro = KokoroTTSProvider(
            kokoro_v1_model(self.models.model_directory("kokoro-82m-v1"))
        )
        piper = PiperTTSProvider(self._piper_models())
        return (
            ProviderChoice(
                "edge", "Microsoft Edge TTS", edge.get_available_voices(), True, False
            ),
            ProviderChoice(
                "kokoro",
                "Kokoro-82M",
                kokoro.get_available_voices(),
                False,
                True,
                "kokoro-82m-v1",
            ),
            ProviderChoice(
                "piper",
                "Piper",
                piper.get_available_voices(),
                False,
                True,
                "piper-lessac-low",
            ),
        )

    def cache_identity(self, provider_id: str) -> str:
        """Include catalog asset versions and digests in preview cache identities."""
        if provider_id == "edge":
            return "edge-adapter-v1"
        if provider_id == "kokoro":
            manifests = (default_manifest("kokoro-82m-v1"),)
        elif provider_id == "piper":
            manifests = tuple(
                model for model in default_catalog() if model.provider_id == "piper"
            )
        else:
            raise ValueError(f"Unknown TTS provider: '{provider_id}'.")
        return hashlib.sha256(
            json.dumps([asdict(model) for model in manifests], sort_keys=True).encode()
        ).hexdigest()

    def _piper_models(self) -> tuple[PiperModel, ...]:
        """Describe all voices without reading installed weights or runtime imports."""
        return tuple(
            descriptor
            for manifest in self.models.list_models()
            if manifest.provider_id == "piper"
            for descriptor in english_models(
                self.models.model_directory(manifest.model_id), manifest.model_id
            )
        )

    def _check_piper_installation(self, model_id: str) -> None:
        """Verify only the requested model, including its marker and model card."""
        if self.models.status(model_id) != InstallationState.INSTALLED:
            raise ModelValidationError(
                f"Install and verify {model_id} in Model library."
            )

    def get(self, provider_id: str) -> TTSProvider:
        """Resolve a verified model-backed provider; call outside the UI thread."""
        with self._lock:
            if self._retain_sessions and provider_id in self._sessions:
                return self._sessions[provider_id]
            if self._selected is not None and self._selected.provider_id == provider_id:
                return self._selected
            if provider_id == "edge":
                provider: TTSProvider = EdgeTTSProvider()
            else:
                if provider_id == "kokoro":
                    model_id = "kokoro-82m-v1"
                elif provider_id == "piper":
                    model_id = None
                else:
                    raise ValueError(f"Unknown TTS provider: '{provider_id}'.")
                if model_id is not None and (
                    self.models.status(model_id) != InstallationState.INSTALLED
                ):
                    raise ModelValidationError(
                        "Install and verify the selected model in Model library."
                    )
                if provider_id == "kokoro":
                    directory = self.models.model_directory(model_id)
                    provider = KokoroTTSProvider(kokoro_v1_model(directory))
                else:
                    provider = PiperTTSProvider(
                        self._piper_models(),
                        validate_installation=self._check_piper_installation,
                    )
            if self._selected is not None and not self._retain_sessions:
                self._selected.close()
            self._selected = provider
            if self._retain_sessions:
                self._sessions[provider_id] = provider
            return provider

    def close(self) -> None:
        """Release the selected model session after any current inference finishes."""
        with self._lock:
            sessions = list(self._sessions.values())
            if self._selected is not None and not self._retain_sessions:
                sessions.append(self._selected)
            self._selected = None
            self._sessions.clear()
            failures = []
            for provider in sessions:
                try:
                    provider.close()
                except Exception as error:
                    # Every retained engine must release even if one close fails.
                    failures.append(error)
            if failures:
                raise failures[0]
