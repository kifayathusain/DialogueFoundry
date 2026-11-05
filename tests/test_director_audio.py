"""Real FFmpeg effects and Director exports using synthetic speech-like tones."""

import asyncio
import math
import wave
from array import array
from dataclasses import replace

import pytest

from tests.test_director import Providers, write_source
from ttsapp.audio_effects import AudioTreatment, apply_treatment
from ttsapp.audio_export import probe_audio
from ttsapp.audio_files import write_pcm_wav
from ttsapp.director import (
    PhoneScope,
    SceneSettings,
    TimingSettings,
    manual_plan,
    scan_folder,
)
from ttsapp.director_runner import render_file, run_batch
from ttsapp.providers.base import CancellationToken, SynthesisResult


def tone(path, token):
    values = array(
        "h",
        (
            round(
                5000 * math.sin(2 * math.pi * 440 * index / 16000)
                + 3000 * math.sin(2 * math.pi * 6000 * index / 16000)
            )
            for index in range(8000)
        ),
    )
    write_pcm_wav((values.tobytes(),), path, 16000, token)


class ToneProviders(Providers):
    def __init__(self):
        super().__init__()

        async def synthesize(request, output_file, cancellation_token=None):
            self.provider.requests.append(request)
            tone(output_file, cancellation_token or CancellationToken())
            return SynthesisResult(output_file, "wav")

        self.provider.synthesize = synthesize


@pytest.mark.integration
def test_phone_changes_only_requested_speech_and_retains_duration(tmp_path):
    token = CancellationToken()
    source = tmp_path / "tone.wav"
    tone(source, token)
    assert (
        apply_treatment(source, tmp_path / "unused.wav", AudioTreatment(), token)
        == source
    )
    output = apply_treatment(
        source, tmp_path / "phone.wav", AudioTreatment(True, 0.002, "paper"), token
    )
    with wave.open(str(source)) as original, wave.open(str(output)) as treated:
        assert original.getnframes() == treated.getnframes()
        original_values = array("h", original.readframes(original.getnframes()))
        treated_values = array("h", treated.readframes(treated.getnframes()))
    assert original_values != treated_values
    assert max(map(abs, treated_values)) < 32767

    # DFT at a retained speech-band component and an attenuated 6 kHz component.
    def magnitude(values, frequency):
        return abs(
            sum(
                value
                * complex(
                    math.cos(2 * math.pi * frequency * index / 16000),
                    -math.sin(2 * math.pi * frequency * index / 16000),
                )
                for index, value in enumerate(values)
            )
        )

    assert magnitude(treated_values, 6000) < 0.25 * magnitude(original_values, 6000)
    assert magnitude(treated_values, 440) > 0.5 * magnitude(original_values, 440)


@pytest.mark.integration
@pytest.mark.parametrize("audio_format", ["wav", "mp3", "m4a"])
def test_batch_media_and_audition_use_same_decisions(tmp_path, audio_format):
    source = tmp_path / "input"
    write_source(source / "lesson.json")
    providers = ToneProviders()
    plan = manual_plan(
        scan_folder(source),
        source,
        tmp_path / "output",
        providers.list_choices()[0],
        audio_format=audio_format,
    )
    item = replace(
        plan.files[0],
        timing=TimingSettings("natural"),
        scene=SceneSettings((PhoneScope("guest", 2, 4),)),
    )
    plan = replace(plan, files=(item,))
    results = asyncio.run(run_batch(plan, providers, CancellationToken()))
    assert results[0].state == "completed", results[0].diagnostic
    destination = plan.output_folder / item.destination_name
    info = probe_audio(destination, CancellationToken())
    # Five half-second speech turns and 1.04s of scripted/resolved silence.
    assert abs(info.duration_seconds - 3.54) < 0.12
    requests = list(providers.provider.requests)
    preview = tmp_path / "directed.wav"
    asyncio.run(
        render_file(
            plan,
            item,
            providers,
            CancellationToken(),
            preview="directed",
            preview_output=preview,
        )
    )
    assert providers.provider.requests[-2:] == requests[:2]
    assert abs(probe_audio(preview, CancellationToken()).duration_seconds - 1.12) < 0.01
    # Final scripted silence is untouched even with phone/room processing.
    if audio_format == "wav":
        with wave.open(str(destination)) as audio:
            audio.setpos(audio.getnframes() - 8000)
            assert not any(audio.readframes(8000))
