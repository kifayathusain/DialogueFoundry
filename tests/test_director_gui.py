"""Actual Tk worker/capture/render checks with synthetic audio and fake providers."""

import ctypes
import time
import tkinter as tk
from dataclasses import replace

import pytest

from tests.test_director import write_source
from tests.test_director_audio import ToneProviders
from ttsapp import director_gui
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


def pump(window, timeout=20):
    deadline = time.monotonic() + timeout
    while window._worker is not None and time.monotonic() < deadline:
        window.update()
        time.sleep(0.01)
    window.update()
    assert window._worker is None, window.status.get()


@pytest.mark.integration
def test_desktop_manual_job_stale_scan_audition_and_retry(tmp_path, monkeypatch):
    root = tk.Tk()
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
        root.destroy()
