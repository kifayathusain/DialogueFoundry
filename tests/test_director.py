"""Batch foundation checks with private sources and fake synthesis only."""

import asyncio
import json
from dataclasses import replace

import pytest

from tests.test_generation import OfflineProvider
from ttsapp import director_runner, generation
from ttsapp.director import (
    IncidentalCue,
    PhoneScope,
    SceneSettings,
    TimingSettings,
    bind_cast,
    edit_file,
    manual_plan,
    preflight,
    resolved_document,
    scan_folder,
    treatments,
)
from ttsapp.director_runner import excerpt_range, run_batch, save_report
from ttsapp.provider_manager import ProviderChoice
from ttsapp.providers.base import CancellationToken


class Providers:
    def __init__(self):
        self.provider = OfflineProvider()

    def get(self, provider_id):
        assert provider_id == self.provider.provider_id
        return self.provider

    def list_choices(self):
        provider = self.provider
        return (
            ProviderChoice(
                provider.provider_id,
                "Fake",
                provider.get_available_voices(),
                False,
                False,
            ),
        )


def write_source(path, *, malformed=False):
    data = {
        "speakers": [{"id": "host", "role": "Host"}, {"id": "guest", "role": "Guest"}],
        "segments": [
            {"speaker": "host", "text": "First?", "pause_after_seconds": 0},
            {"speaker": "guest", "text": "Yes."},
            {"speaker": "host", "text": "Tell me more?", "pause_after_seconds": 0.3},
            {
                "speaker": "guest",
                "text": "A longer considered answer to your question.",
            },
            {"speaker": "host", "text": "Thank you.", "pause_after_seconds": 0.5},
        ],
    }
    if malformed:
        data["segments"][0]["speaker"] = "unknown"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def batch(tmp_path):
    source = tmp_path / "in"
    source.mkdir()
    write_source(source / "a.json")
    write_source(source / "b.json")
    providers = Providers()
    plan = manual_plan(
        scan_folder(source),
        source,
        tmp_path / "out",
        providers.list_choices()[0],
        audio_format="wav",
    )
    return plan, providers


def test_discovery_excludes_projects_and_preserves_invalid_candidates(tmp_path):
    write_source(tmp_path / "good.json")
    write_source(tmp_path / "bad.json", malformed=True)
    write_source(tmp_path / "nested" / "child.json")
    (tmp_path / "project.json").write_text(
        '{"kind":"project","document":{"speakers":[]}}'
    )
    (tmp_path / "broken.json").write_text('{"speakers": [')
    scan = scan_folder(tmp_path)
    assert [item.file_id for item in scan.files] == [
        "bad.json",
        "broken.json",
        "good.json",
    ]
    assert (
        "unknown" in scan.files[0].error.lower()
        or "declared" in scan.files[0].error.lower()
    )
    assert scan.files[1].error
    assert len(scan.excluded) == 1
    assert len(scan_folder(tmp_path, True).files) == 4


def test_timing_only_omitted_nonfinal_transitions_and_no_source_edits(batch):
    plan, _ = batch
    item = replace(plan.files[0], timing=TimingSettings("natural"))
    document = resolved_document(item)
    assert [segment.pause_after_seconds for segment in document.segments] == [
        0,
        0.12,
        0.3,
        0.12,
        0.5,
    ]
    assert item.source.document.segments[1].pause_after_seconds == 0
    assert [segment.text for segment in document.segments] == [
        segment.text for segment in item.source.document.segments
    ]


def test_conflicts_scopes_and_changed_sources_block_before_render(batch):
    plan, providers = batch
    plan = edit_file(plan, "b.json", destination_name="a.wav")
    assert all(
        "Duplicate" in errors[0]
        for errors in preflight(plan, providers.list_choices()).values()
    )
    plan = edit_file(plan, "b.json", destination_name="renamed.wav")
    plan = edit_file(plan, "a.json", destination_name="../escape.wav")
    assert preflight(plan, providers.list_choices())["a.json"]
    plan = edit_file(plan, "a.json", destination_name="a.wav")
    plan.files[0].source.path.write_text("{}")
    assert (
        "Source changed"
        in preflight(plan, providers.list_choices(), check_sources=True)["a.json"][0]
    )


def test_named_binding_is_explicit_and_phone_is_scoped(batch):
    plan, _ = batch
    plan = bind_cast(plan, (("a.json", "guest"), ("b.json", "host")), "voice")
    assert "cast" in plan.files[0].manual_fields
    scene = SceneSettings(
        (PhoneScope("guest", 2, 3),), 0.001, (IncidentalCue(3, "paper"),)
    )
    item = replace(plan.files[0], scene=scene)
    effects = treatments(item)
    assert [index for index, effect in effects.items() if effect.telephone] == [2]
    assert effects[3].cue == "paper"
    assert excerpt_range(item) == (0, 2)


def test_continue_cancel_retry_and_report_privacy(batch, monkeypatch, tmp_path):
    plan, providers = batch
    calls = []

    async def render(plan, item, providers, token, **kwargs):
        calls.append(item.source.file_id)
        if item.source.file_id == "a.json":
            raise RuntimeError("PRIVATE DIALOGUE")
        return plan.output_folder / item.destination_name

    monkeypatch.setattr(director_runner, "render_file", render)
    results = asyncio.run(run_batch(plan, providers, CancellationToken()))
    assert [item.state for item in results] == ["failed", "completed"]
    assert calls == ["a.json", "b.json"]
    report = save_report(plan, results, tmp_path / "report.json").read_text()
    assert "PRIVATE DIALOGUE" not in report
    assert "First?" not in report
    calls.clear()
    asyncio.run(
        run_batch(
            plan,
            providers,
            CancellationToken(),
            previous=results,
            retry_ids=frozenset({"a.json"}),
        )
    )
    assert calls == ["a.json"]
    with pytest.raises(ValueError, match="Retry only"):
        asyncio.run(
            run_batch(
                plan,
                providers,
                CancellationToken(),
                previous=results,
                retry_ids=frozenset({"b.json"}),
            )
        )
    token = CancellationToken()
    token.cancel()
    cancelled = asyncio.run(run_batch(plan, providers, token))
    assert all(item.state == "cancelled" for item in cancelled)
    calls.clear()
    stopped = asyncio.run(
        run_batch(replace(plan, failure_policy="stop"), providers, CancellationToken())
    )
    assert calls == ["a.json"]
    assert stopped[1].state == "cancelled"


def test_real_service_runner_cleans_job_audio_and_preserves_final_pause(
    batch, monkeypatch
):
    plan, providers = batch
    recorded = []

    def export(sources, destination, settings, token, **kwargs):
        import wave

        with wave.open(str(sources[-1])) as audio:
            assert audio.getnframes() == 8000
        recorded.extend(sources)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"final")
        return destination

    monkeypatch.setattr(generation, "export_audio", export)
    results = asyncio.run(run_batch(plan, providers, CancellationToken()))
    assert all(item.state == "completed" for item in results)
    assert not any(path.exists() for path in recorded)
    assert len(providers.provider.requests) == 10


def test_active_cancellation_retains_existing_output_and_cleans_pcm(batch):
    plan, providers = batch
    plan.output_folder.mkdir()
    destination = plan.output_folder / "a.wav"
    destination.write_bytes(b"previous final audio")
    plan = edit_file(plan, "a.json", overwrite=True)
    providers.provider.cancel_on_call = 2
    results = asyncio.run(run_batch(plan, providers, CancellationToken()))
    assert [item.state for item in results] == ["cancelled", "cancelled"]
    assert destination.read_bytes() == b"previous final audio"
    assert not (plan.output_folder / "b.wav").exists()


def test_source_change_between_files_is_revalidated(batch, monkeypatch):
    plan, providers = batch
    calls = []

    async def render(plan, item, providers, token, **kwargs):
        calls.append(item.source.file_id)
        plan.files[1].source.path.write_text("{}")
        return plan.output_folder / item.destination_name

    monkeypatch.setattr(director_runner, "render_file", render)
    results = asyncio.run(run_batch(plan, providers, CancellationToken()))
    assert calls == ["a.json"]
    assert results[1].state == "failed"
    assert "rescan" in results[1].diagnostic.lower()
