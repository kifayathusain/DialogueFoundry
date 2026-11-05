"""Actual Tk worker/capture/render checks with synthetic audio and fake providers."""

import ctypes
import time
import tkinter as tk
from dataclasses import replace

import pytest

from tests.test_director import write_source
from tests.test_director_audio import ToneProviders
from tests.test_director_direction import (
    GenderProviders,
    fake_openai,
    gender_batch,
    proposal_for,
)
from ttsapp import director_gui
from ttsapp.config import DEFAULT_DIRECTOR_DIRECTION
from ttsapp.director import PhoneScope, SceneSettings
from ttsapp.director_gui import AudioDirectorWindow, DirectorEvent
from ttsapp.models.manager import ModelManager


class UIProviders(ToneProviders):
    def __init__(self, directory):
        super().__init__()
        self.models = ModelManager(directory)
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture(scope="module")
def director_root():
    """Reuse one Tcl interpreter for the module's independent Director windows."""
    root = tk.Tk()
    yield root
    root.destroy()


def pump(window, timeout=20):
    deadline = time.monotonic() + timeout
    while window._worker is not None and time.monotonic() < deadline:
        window.update()
        time.sleep(0.01)
    window.update()
    assert window._worker is None, window.status.get()


@pytest.mark.integration
def test_desktop_manual_job_stale_scan_audition_and_retry(
    tmp_path, monkeypatch, director_root
):
    root = director_root
    providers = UIProviders(tmp_path / "models")
    window = AudioDirectorWindow(root, providers)
    monkeypatch.setattr(window._player, "play", lambda path: None)
    try:
        source = tmp_path / "Lessons"
        write_source(source / "a.json")
        write_source(source / "bad.json", malformed=True)
        window.source.set(str(source))
        window.destination.set(str(tmp_path / "output"))
        window.audio_format.set("wav")
        window.scan()
        pump(window)
        assert window.plan is not None, window.status.get()
        assert "1 ready" in window.summary.get()
        assert "1 need attention" in window.summary.get()
        window.files.selection_set("a.json")
        window._select_file()
        preset = tmp_path / "cast-preset.json"
        monkeypatch.setattr(
            director_gui.filedialog, "asksaveasfilename", lambda **kwargs: str(preset)
        )
        monkeypatch.setattr(
            director_gui.filedialog, "askopenfilename", lambda **kwargs: str(preset)
        )
        window.save_preset()
        pump(window)
        assert preset.is_file()
        window.load_preset()
        pump(window)
        assert not window.errors["a.json"], window.status.get()
        window.plan = replace(
            window.plan,
            files=(
                replace(
                    window.plan.files[0],
                    scene=SceneSettings((PhoneScope("guest", 2, 4),)),
                ),
                window.plan.files[1],
            ),
        )
        window.preview("directed")
        pump(window)
        assert window._preview.is_file(), window.status.get()
        window.generate()
        pump(window)
        assert [result.state for result in window.results] == ["completed", "failed"], (
            window.status.get()
        )
        assert (tmp_path / "output" / "a.wav").is_file()
        assert window._report.is_file()
        window.files.selection_set("bad.json")
        window.generate(retry=True)
        pump(window)
        assert window.results[0].state == "completed"
        # A late scan cannot overwrite newer source selection.
        old_plan = window.plan
        old_revision = window._revision
        window.source.set(str(tmp_path / "other"))
        window._events.put(DirectorEvent(old_revision, "Scan", (old_plan, (), {})))
        window._poll()
        assert window.plan is None
        window.geometry("1024x768")
        window.update()
        dpi = ctypes.windll.user32.GetDpiForWindow(window.winfo_id())
        assert dpi > 0
        window.focus_force()
        window.update()
        window.direction.focus_set()
        window.update()
        window.direction.event_generate("<Tab>")
        window.update()
        assert window.focus_get() is not None
        assert window.focus_get() is not window.direction
    finally:
        if window._worker is not None:
            window.cancel()
            pump(window)
        window.close()
        deadline = time.monotonic() + 5
        while window.winfo_exists() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        assert not window.winfo_exists()
        assert providers.closed


@pytest.mark.integration
def test_openai_cast_review_manual_rebuild_errors_and_rendering(
    tmp_path, monkeypatch, director_root
):
    import json

    source_plan, _ = gender_batch(tmp_path)
    monkeypatch.setenv("TTS_DIRECTOR_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TTS_DIRECTOR_LLM_MODEL", "configured-openai-model")
    root = director_root
    providers = GenderProviders(tmp_path / "ui-models")
    window = AudioDirectorWindow(root, providers)
    monkeypatch.setattr(window._player, "play", lambda path: None)
    try:
        assert window.direction.get("1.0", "end").strip() == DEFAULT_DIRECTOR_DIRECTION
        assert "OpenAI" in window.planner_summary.get()
        assert "configured-openai-model" in window.planner_summary.get()
        window.direction.delete("1.0", "end")
        direction = "My edited direction. Use the declared metadata."
        window.direction.insert("1.0", direction)
        window.source.set(str(source_plan.input_folder))
        window.destination.set(str(tmp_path / "ui-output"))
        window.audio_format.set("wav")
        window.scan()
        pump(window)
        assert window.direction.get("1.0", "end").strip() == direction
        assert window.cast.item("host", "values")[0:4] == (
            "male-a",
            "male",
            providers.provider.provider_id,
            "Voice A",
        )
        assert window.cast.item("guest", "values")[0:4] == (
            "female-a",
            "female",
            providers.provider.provider_id,
            "Voice C",
        )
        proposal = proposal_for(window.plan)
        calls = fake_openai(monkeypatch, json.dumps(proposal))
        window.use_ai.set(True)
        window.cloud.set(True)
        original = window.plan
        window.build_plan()
        pump(window)
        assert calls == []
        assert window.plan is original
        assert "local loopback" in window.status.get()
        window.offline.set(False)
        window.excerpts.set(True)
        window.build_plan()
        pump(window)
        assert not window.errors["lesson.json"], window.status.get()
        payload = calls[-1][3]
        assert payload["model"] == "configured-openai-model"
        assert json.loads(payload["messages"][1]["content"])["direction"] == direction
        assert window.cast.item("host", "values")[4] == "AI match"
        window.cast.selection_set("host")
        window.voice.set("male-b")
        window.apply_voice()
        corrected = window.plan
        failed_calls = fake_openai(monkeypatch, "private body", status=401)
        window.build_plan()
        pump(window)
        assert "authentication" in window.status.get()
        assert failed_calls[0][0].closed
        assert window.plan is corrected
        assert window.cast.item("host", "values")[0] == "male-b"
        fake_openai(monkeypatch, "not JSON")
        window.build_plan()
        pump(window)
        assert "valid JSON" in window.status.get()
        assert window.plan is corrected
        fake_openai(monkeypatch, json.dumps(proposal))
        window.build_plan()
        pump(window)
        assert window.cast.item("host", "values")[0] == "male-b"
        assert window.cast.item("host", "values")[4] == "Manual override"
        assert window.cast.item("guest", "values")[4] == "AI match"
        assert "manual" in window.details.get("1.0", "end")
        window.accept_review()
        window.preview("directed")
        pump(window)
        assert window._preview.is_file(), window.status.get()
        assert [request.voice_id for request in providers.provider.requests] == [
            "male-b",
            "female-a",
        ]
        window.generate()
        pump(window)
        assert window.results[0].state == "completed", window.status.get()
        assert [request.voice_id for request in providers.provider.requests[2:4]] == [
            "male-b",
            "female-a",
        ]
        assert window.direction.get("1.0", "end").strip() == direction
    finally:
        if window._worker is not None:
            window.cancel()
            pump(window)
        window.close()
        deadline = time.monotonic() + 5
        while window.winfo_exists() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
