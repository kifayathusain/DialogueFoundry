"""Mixed casting acceptance through public discovery/validate/render commands."""

import asyncio
import json
import math
import struct
import wave
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ttsapp import director_cli, generation
from ttsapp.audio_export import probe_audio
from ttsapp.audio_files import write_pcm_wav
from ttsapp.audio_process import run_audio_process
from ttsapp.cli import run_cli
from ttsapp.models.manager import InstallationState
from ttsapp.provider_manager import ProviderChoice
from ttsapp.providers.base import (
    CancellationToken,
    ProviderCapabilities,
    SynthesisResult,
    VoiceMetadata,
)

EXAMPLE = Path("examples/audio_director")


class CastProvider:
    """Generate different native layouts while recording exact routed requests."""

    def __init__(self, provider_id, voice_id, locale, rate):
        self.provider_id = provider_id
        self.display_name = provider_id
        self.voices = (VoiceMetadata(voice_id, voice_id, locale),)
        self.rate = rate
        self.requests = []
        self.fail = False
        self.cancel = False
        self.closed = 0

    def get_available_voices(self):
        return self.voices

    def get_capabilities(self):
        return ProviderCapabilities(
            online=self.provider_id == "edge",
            audio_formats=("mp3",) if self.provider_id == "edge" else ("wav",),
            supports_speed=self.provider_id != "edge",
            max_text_characters=60,
        )

    def validate_configuration(self, request):
        if request.voice_id not in {v.voice_id for v in self.voices}:
            raise ValueError("Wrong voice routed to provider")
        if request.speed is not None and self.provider_id == "edge":
            raise ValueError("Edge speed unsupported")
        if len(request.text) > 60:
            raise ValueError("Provider chunk limit exceeded")

    async def synthesize(self, request, output_file, cancellation_token=None):
        self.validate_configuration(request)
        self.requests.append(request)
        if self.fail:
            output_file.write_bytes(b"partial provider audio")
            raise RuntimeError("Second provider failed")
        if self.cancel:
            raise asyncio.CancelledError
        token = cancellation_token or CancellationToken()
        samples = [
            round(
                4000
                * (
                    math.sin(i * 2 * math.pi * 800 / self.rate)
                    + math.sin(i * 2 * math.pi * 6000 / self.rate)
                )
            )
            for i in range(self.rate // 5)
        ]
        pcm = struct.pack(f"<{len(samples)}h", *samples)
        native = output_file.with_suffix(".wav")
        write_pcm_wav((pcm,), native, self.rate, token)
        if request.audio_format == "mp3":
            run_audio_process(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-i",
                    str(native),
                    "-c:a",
                    "libmp3lame",
                    str(output_file),
                ],
                token,
            )
        return SynthesisResult(output_file, request.audio_format)

    def close(self):
        self.closed += 1


class CastProviders:
    """A manager with no real inference or network dependencies."""

    def __init__(self):
        self.engines = {
            "kokoro": CastProvider("kokoro", "bm_george", "en-GB", 24000),
            "piper": CastProvider("piper", "en_US-lessac-low", "en-US", 22050),
            "edge": CastProvider("edge", "en-US-AriaNeural", "en-US", 44100),
        }

    def get(self, provider_id):
        return self.engines[provider_id]

    def list_choices(self):
        return tuple(
            ProviderChoice(key, key, engine.voices, key == "edge", key != "edge")
            for key, engine in self.engines.items()
        )

    def close(self):
        for engine in self.engines.values():
            engine.close()


@pytest.fixture
def mixed_job(tmp_path, monkeypatch):
    manager = CastProviders()
    monkeypatch.setattr(director_cli, "ProviderManager", lambda *args, **kw: manager)
    monkeypatch.setattr(director_cli, "find_spec", lambda package: True)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    source = tmp_path / "conversation.json"
    source.write_bytes((EXAMPLE / "mixed.conversation.json").read_bytes())
    direction = tmp_path / "direction.json"
    direction.write_bytes((EXAMPLE / "mixed.direction.json").read_bytes())
    output = tmp_path / "conversation.wav"
    plan = tmp_path / "plan.json"
    validate = [
        "director",
        "validate",
        "--input",
        str(source),
        "--direction",
        str(direction),
        "--output",
        str(output),
        "--plan",
        str(plan),
    ]
    return manager, source, direction, output, plan, validate


@pytest.mark.integration
@pytest.mark.parametrize("guest_provider", ["piper", "edge"])
def test_mixed_render_routes_cast_and_guest_phone_only(
    mixed_job, monkeypatch, guest_provider
):
    manager, source, direction, output, plan, validate = mixed_job
    raw = json.loads(direction.read_text())
    if guest_provider == "edge":
        raw["offline"] = False
        raw["settings"]["voices"]["guest"] = {
            "provider": "edge",
            "voice": "en-US-AriaNeural",
        }
    direction.write_text(json.dumps(raw))
    effects = []
    apply = generation.apply_treatment

    def capture(source_audio, destination, treatment, token):
        with wave.open(str(source_audio)) as audio:
            effects.append(
                (
                    treatment.telephone,
                    audio.getframerate(),
                    audio.getnchannels(),
                    audio.getsampwidth(),
                )
            )
        return apply(source_audio, destination, treatment, token)

    monkeypatch.setattr(generation, "apply_treatment", capture)
    assert run_cli(validate) == 0
    assert all(not e.requests for e in manager.engines.values())
    review = json.loads(plan.read_text())
    assert [t["provider"] for t in review["turns"]] == [
        "kokoro",
        guest_provider,
        "kokoro",
        guest_provider,
    ]
    assert review["turns"][0]["pause_after_seconds"] == 0
    assert review["cast"]["host"]["match_evidence"]["catalog_locale"] == "en-GB"
    assert "authoritative: judgment call" in review["cast"]["host"]["judgment_calls"][0]
    assert "warm: judgment call" in review["cast"]["guest"]["judgment_calls"][0]
    assert run_cli(["director", "render", "--plan", str(plan)]) == 0
    data = json.loads(source.read_text())
    for speaker, provider_id in (("host", "kokoro"), ("guest", guest_provider)):
        requests = manager.engines[provider_id].requests
        assert [r.text for r in requests] == [
            s["text"] for s in data["segments"] if s["speaker"] == speaker
        ]
        assert len({r.voice_id for r in requests}) == 1
    assert effects == [(False, 24000, 1, 2), (True, 24000, 1, 2)] * 2
    probe = probe_audio(output, CancellationToken())
    assert probe.sample_rate == 32000
    with wave.open(str(output)) as audio:
        audio.setpos(audio.getnframes() - 16000)
        assert audio.readframes(16000) == b"\0\0" * 16000
    assert not list(output.parent.glob("tts-director-*"))
    assert all(e.closed == 2 for e in manager.engines.values())


@pytest.mark.integration
@pytest.mark.parametrize("failure", ["fail", "cancel"])
def test_second_provider_failure_or_cancel_cleans_and_preserves_output(
    mixed_job, failure
):
    manager, _, _, output, plan, validate = mixed_job
    output.write_bytes(b"existing audio")
    validate.append("--overwrite")
    assert run_cli(validate) == 0
    setattr(manager.engines["piper"], failure, True)
    assert run_cli(["director", "render", "--plan", str(plan)]) == (
        130 if failure == "cancel" else 1
    )
    assert output.read_bytes() == b"existing audio"
    assert len(manager.engines["kokoro"].requests) == 1
    assert len(manager.engines["piper"].requests) == 1
    assert all(e.closed == 2 for e in manager.engines.values())
    assert not list(output.parent.glob("tts-director-*"))


@pytest.mark.parametrize(
    "defect",
    [
        "speaker",
        "provider",
        "voice_pair",
        "offline",
        "unavailable",
        "required",
        "scoped_speed",
        "job_speed",
        "source_speed",
        "malformed_pair",
        "missing_asset",
        "runtime",
        "unknown_preference",
        "turn_speed",
    ],
)
def test_casting_errors_block_all_synthesis(mixed_job, defect, monkeypatch):
    manager, source, direction, output, plan, validate = mixed_job
    raw = json.loads(direction.read_text())
    voices = raw["settings"]["voices"]
    if defect == "speaker":
        voices["missing"] = "bm_george"
    elif defect == "provider":
        voices["guest"]["provider"] = "missing"
    elif defect == "voice_pair":
        voices["guest"]["voice"] = "bm_george"
    elif defect == "malformed_pair":
        voices["guest"] = {"voice": "en_US-lessac-low"}
    elif defect == "unknown_preference":
        raw["speaker_preferences"]["unknown"] = {"locale": "en-US"}
    elif defect == "missing_asset":
        engine = manager.engines["piper"]
        engine.voices = (replace(engine.voices[0], model_id="missing-model"),)
        manager.models = SimpleNamespace(
            status=lambda model: InstallationState.NOT_INSTALLED
        )
    elif defect == "runtime":
        monkeypatch.setattr(
            director_cli,
            "find_spec",
            lambda package: None if package == "piper" else True,
        )
    elif defect == "unavailable":

        def unavailable(request):
            raise ValueError("Unavailable assets")

        monkeypatch.setattr(
            manager.engines["piper"], "validate_configuration", unavailable
        )
    elif defect == "required":
        raw["speaker_preferences"]["guest"]["locale"] = "en-AU"
    else:
        voices["guest"] = {"provider": "edge", "voice": "en-US-AriaNeural"}
        raw["offline"] = defect == "offline"
        if defect == "scoped_speed":
            raw["settings"]["speaker_speeds"] = {"guest": 1.1}
        elif defect == "turn_speed":
            raw["settings"]["turns"] = [{"segment": 2, "speed": 1.1}]
        elif defect == "job_speed":
            raw["settings"]["speed"] = 1.1
        elif defect == "source_speed":
            data = json.loads(source.read_text())
            data["segments"][1]["speech"] = {"speed": 1.1}
            source.write_text(json.dumps(data))
    direction.write_text(json.dumps(raw))
    assert run_cli(validate) == 1
    assert not output.exists() and not plan.exists()
    assert all(not e.requests for e in manager.engines.values())


def test_host_speed_does_not_reject_guest_edge(mixed_job):
    _, _, direction, _, _, validate = mixed_job
    raw = json.loads(direction.read_text())
    raw["offline"] = False
    raw["settings"]["voices"]["guest"] = {
        "provider": "edge",
        "voice": "en-US-AriaNeural",
    }
    raw["settings"]["speaker_speeds"] = {"host": 1.1}
    direction.write_text(json.dumps(raw))
    assert run_cli(validate) == 0


def test_required_language_and_explicit_assignment_precedence(mixed_job):
    _, _, direction, _, plan, validate = mixed_job
    raw = json.loads(direction.read_text())
    raw["speaker_preferences"] = {"guest": {"language": "en", "required": True}}
    direction.write_text(json.dumps(raw))
    assert run_cli(validate) == 0
    plan.unlink()
    raw["speaker_preferences"]["guest"]["language"] = "fr"
    direction.write_text(json.dumps(raw))
    assert run_cli(validate) == 1


def test_changed_mixed_cast_is_stale_before_synthesis(mixed_job, capsys):
    manager, _, direction, _, plan, validate = mixed_job
    assert run_cli(validate) == 0
    raw = json.loads(direction.read_text())
    raw["settings"]["voices"]["guest"] = "bm_george"
    raw["speaker_preferences"]["guest"]["locale"] = "en-GB"
    direction.write_text(json.dumps(raw))
    assert run_cli(["director", "render", "--plan", str(plan)]) == 1
    assert "Stale plan" in capsys.readouterr().err
    assert all(not e.requests for e in manager.engines.values())


@pytest.mark.integration
@pytest.mark.parametrize("audio_format,codec", [("mp3", "mp3"), ("m4a", "aac")])
def test_mixed_compressed_export_honors_final_settings(mixed_job, audio_format, codec):
    _, _, direction, output, plan, validate = mixed_job
    raw = json.loads(direction.read_text())
    raw["export"] = {"sample_rate": 44100, "channels": 2, "normalize": True}
    if audio_format == "mp3":
        raw["export"]["mp3_bitrate_kbps"] = 128
    direction.write_text(json.dumps(raw))
    destination = output.with_suffix("." + audio_format)
    validate[validate.index(str(output))] = str(destination)
    assert run_cli(validate) == 0
    assert run_cli(["director", "render", "--plan", str(plan)]) == 0
    info = probe_audio(destination, CancellationToken())
    assert (info.codec, info.sample_rate, info.channels) == (codec, 44100, 2)
    if audio_format == "mp3":
        assert info.bitrate == 128000


def test_legacy_strings_source_defaults_and_distinct_catalog_choices(mixed_job):
    manager, source, direction, _, plan, validate = mixed_job
    raw = json.loads(direction.read_text())
    raw.pop("speaker_preferences")
    raw["settings"]["voices"] = {"guest": "bm_george"}
    direction.write_text(json.dumps(raw))
    assert run_cli(validate) == 0
    review = json.loads(plan.read_text())
    assert review["cast"]["host"]["origin"] == "Explicit source default"
    assert review["cast"]["host"]["reused_with"] == ["guest"]
    plan.unlink()
    data = json.loads(source.read_text())
    data["speakers"][0].pop("voice_defaults")
    source.write_text(json.dumps(data))
    raw["settings"]["voices"] = {}
    raw["speaker_preferences"] = {"guest": {"locale": "en-AU", "required": False}}
    direction.write_text(json.dumps(raw))
    engine = manager.engines["kokoro"]
    engine.voices += (replace(engine.voices[0], voice_id="bm_lewis"),)
    assert run_cli(validate) == 0
    review = json.loads(plan.read_text())
    assert {r["voice"] for r in review["cast"].values()} == {"bm_george", "bm_lewis"}
    assert review["cast"]["guest"]["fallback"]


def test_discovery_reports_exact_model_speaker_locale_and_readiness(
    tmp_path, monkeypatch, capsys
):
    from ttsapp.models.manager import ModelManager
    from ttsapp.provider_manager import ProviderManager

    models = ModelManager(tmp_path / "models")
    manager = ProviderManager(models)
    monkeypatch.setattr(director_cli, "ProviderManager", lambda *args, **kw: manager)
    monkeypatch.setattr(
        models,
        "status",
        lambda model: (
            InstallationState.INSTALLED
            if model == "kokoro-82m-v1"
            else InstallationState.NOT_INSTALLED
        ),
    )
    assert run_cli(["director", "discover"]) == 0
    inventory = json.loads(capsys.readouterr().out)
    providers = {p["provider_id"]: p for p in inventory["providers"]}
    assert all(
        v["readiness"] == "online_unchecked" for v in providers["edge"]["voices"]
    )
    assert providers["kokoro"]["voices"][0]["readiness"] == "local_assets_verified"
    voice = next(
        v
        for v in providers["piper"]["voices"]
        if v["voice_id"] == "en_GB-vctk-medium:speaker_108"
    )
    assert voice["speaker_id"] == 108
    assert voice["model_id"] == "piper-en_gb-vctk-medium"
    assert voice["provider"] == "piper" and voice["catalog_locale"] == "en-GB"
    assert voice["readiness"] == "local_assets_unavailable"
    assert run_cli(["director", "discover", "--offline"]) == 0
    offline = json.loads(capsys.readouterr().out)
    assert offline["offline"] is True
    assert {p["provider_id"] for p in offline["providers"]} == {"piper", "kokoro"}
