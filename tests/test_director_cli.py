"""Verify the public Director command boundary with the shared offline provider."""

import json
from pathlib import Path

import pytest

from tests.test_director import Providers
from ttsapp import director_cli
from ttsapp.cli import run_cli

EXAMPLE = Path("examples/audio_director")


@pytest.fixture
def job(tmp_path, monkeypatch):
    providers = Providers()
    providers.close = lambda: None
    monkeypatch.setattr(director_cli, "ProviderManager", lambda models: providers)
    raw = json.loads((EXAMPLE / "telephone.direction.json").read_text())
    raw["settings"]["provider"] = providers.provider.provider_id
    direction = tmp_path / "direction.json"
    direction.write_text(json.dumps(raw))
    output = tmp_path / "interview.wav"
    plan = tmp_path / "plan.json"
    validate = [
        "director",
        "validate",
        "--input",
        str(EXAMPLE / "Lessons/03_telephone_interview.json"),
        "--direction",
        str(direction),
        "--output",
        str(output),
        "--plan",
        str(plan),
    ]
    return providers, direction, output, plan, validate


def test_discover(capsys):
    assert run_cli(["director", "discover"]) == 0
    inventory = json.loads(capsys.readouterr().out)
    assert inventory["assets"] and inventory["effects"]["phone"]
    assert all(choice["voices"] for choice in inventory["providers"])


@pytest.mark.parametrize("cancel", [False, True])
def test_review_and_render(job, cancel, tmp_path, monkeypatch):
    providers, _, output, plan, validate = job
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    assert run_cli(validate) == 0
    assert not providers.provider.requests
    review = json.loads(plan.read_text())
    assert not review["preferences"]["guest"]["matched"]
    assert [t["effect"]["telephone"] for t in review["turns"]] == [
        False,
        True,
        False,
        True,
        False,
    ]
    assert review["turns"][2]["pause_after_seconds"] == 0
    render = ["director", "render", "--plan", str(plan)]
    if cancel:
        providers.provider.cancel_on_call = 2
    assert run_cli(render) == (130 if cancel else 0)
    assert output.exists() != cancel
    assert not list(tmp_path.glob("tts-director-*"))
    if not cancel:
        assert run_cli(render) == 1


@pytest.mark.parametrize("defect", ["required", "speaker", "effect", "assets", "stale"])
def test_invalid_job_never_synthesizes(job, defect, monkeypatch):
    providers, direction, _, plan, validate = job
    raw = json.loads(direction.read_text())
    if defect == "required":
        raw["required"] = True
    elif defect == "speaker":
        raw["settings"]["voices"]["missing"] = "voice"
    elif defect == "effect":
        raw["settings"]["scene"]["reverb"] = True
    elif defect == "assets":

        def unavailable(request):
            raise ValueError("missing model")

        monkeypatch.setattr(providers.provider, "validate_configuration", unavailable)
    else:
        assert run_cli(validate) == 0
        raw["settings"]["scene"]["phone"] = []
    direction.write_text(json.dumps(raw))
    command = (
        ["director", "render", "--plan", str(plan)] if defect == "stale" else validate
    )
    assert run_cli(command) == 1
    assert not providers.provider.requests
