"""Fast choice metadata and explicit selected-session cleanup."""

from pathlib import Path

import pytest

from ttsapp.models.assets import ModelValidationError
from ttsapp.models.manager import InstallationState, ModelManager
from ttsapp.provider_manager import ProviderManager
from ttsapp.providers.base import SynthesisRequest


def test_choices_do_not_create_model_storage_and_edge_needs_no_model(
    tmp_path: Path,
) -> None:
    storage = tmp_path / "models"
    providers = ProviderManager(ModelManager(storage))
    assert [choice.provider_id for choice in providers.list_choices()] == [
        "edge",
        "kokoro",
        "piper",
    ]
    assert providers.get("edge") is providers.get("edge")
    assert not storage.exists()


def test_missing_model_has_actionable_error(tmp_path: Path) -> None:
    providers = ProviderManager(ModelManager(tmp_path))
    with pytest.raises(ModelValidationError, match="Model library"):
        providers.get("kokoro")


def test_switching_provider_releases_previous_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    models = ModelManager(tmp_path)
    monkeypatch.setattr(models, "status", lambda model_id: InstallationState.INSTALLED)
    providers = ProviderManager(models)
    piper = providers.get("piper")
    assert providers.get("piper") is piper
    released = []
    monkeypatch.setattr(piper, "close", lambda: released.append(True))
    providers.get("edge")
    assert released == [True]
    providers.close()


def test_selected_provider_skips_disk_scan_until_session_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    models = ModelManager(tmp_path)
    checks = []

    def status(model_id: str) -> InstallationState:
        checks.append(model_id)
        return InstallationState.INSTALLED

    monkeypatch.setattr(models, "status", status)
    providers = ProviderManager(models)
    provider = providers.get("kokoro")
    assert providers.get("kokoro") is provider
    assert checks == ["kokoro-82m-v1"]
    providers.close()
    assert providers.get("kokoro") is not provider
    assert checks == ["kokoro-82m-v1", "kokoro-82m-v1"]


def test_piper_checks_only_requested_installation_on_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    models = ModelManager(tmp_path)
    checks = []

    def status(model_id: str) -> InstallationState:
        checks.append(model_id)
        return InstallationState.NOT_INSTALLED

    monkeypatch.setattr(models, "status", status)
    providers = ProviderManager(models)
    piper = providers.get("piper")
    assert checks == []
    with pytest.raises(ModelValidationError, match="piper-en_gb-vctk-medium"):
        piper.prepare("en_GB-vctk-medium:speaker_108")
    assert checks == ["piper-en_gb-vctk-medium"]


def test_piper_prevalidation_checks_installation_before_preview_cache_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    models = ModelManager(tmp_path)
    monkeypatch.setattr(models, "status", lambda model_id: InstallationState.CORRUPT)
    provider = ProviderManager(models).get("piper")
    with pytest.raises(ModelValidationError, match="piper-lessac-low.*Model library"):
        provider.validate_configuration(
            SynthesisRequest("Hello", "en_US-lessac-low", "wav")
        )


@pytest.mark.parametrize("fail_close", [False, True])
def test_retained_cast_sessions_reuse_and_close_every_provider(
    tmp_path, monkeypatch, fail_close
):
    models = ModelManager(tmp_path)
    monkeypatch.setattr(models, "status", lambda model: InstallationState.INSTALLED)
    manager = ProviderManager(models, retain_sessions=True)
    kokoro = manager.get("kokoro")
    piper = manager.get("piper")
    edge = manager.get("edge")
    closed = []

    def close_kokoro():
        closed.append("kokoro")
        if fail_close:
            raise RuntimeError("Close failed")

    monkeypatch.setattr(kokoro, "close", close_kokoro)
    monkeypatch.setattr(piper, "close", lambda: closed.append("piper"))
    monkeypatch.setattr(edge, "close", lambda: closed.append("edge"))
    assert manager.get("kokoro") is kokoro
    assert manager.get("piper") is piper
    assert not closed
    if fail_close:
        with pytest.raises(RuntimeError, match="Close failed"):
            manager.close()
    else:
        manager.close()
    assert closed == ["kokoro", "piper", "edge"]
    manager.close()
    assert closed == ["kokoro", "piper", "edge"]
