"""Pinned unquantized Kokoro-82M v1.0 and complete English voice choices."""

from pathlib import Path

from ..providers.base import VoiceMetadata
from ..providers.kokoro import KokoroModel
from .assets import assets_from_manifest
from .catalog import default_manifest


def kokoro_v1_model(model_directory: Path) -> KokoroModel:
    """Describe verified upstream assets without downloading or opening them."""
    assets = assets_from_manifest(default_manifest("kokoro-82m-v1"), model_directory)
    voices = tuple(
        VoiceMetadata(
            identifier,
            f"{identifier[3:].title()} ({'British' if identifier[0] == 'b' else 'US'} English)",
            "en-GB" if identifier[0] == "b" else "en-US",
            "kokoro-82m-v1",
            "Apache-2.0",
            gender="female" if identifier[1] == "f" else "male",
        )
        for identifier in default_manifest("kokoro-82m-v1").voices
    )
    return KokoroModel(
        assets["kokoro-v1.0.onnx"],
        assets["voices-v1.0.bin"],
        voices,
    )
