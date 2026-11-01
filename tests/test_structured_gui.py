"""Actual Windows Tk acceptance with injected metadata and fake providers only."""

import ctypes
import json
import threading
import time
from pathlib import Path

import pytest

from tests.test_structured_generation import StructuredProvider
from ttsapp import gui
from ttsapp.conversation_document import load_document, parse_document_data
from ttsapp.models.manager import ModelManager
from ttsapp.provider_manager import ProviderManager


class FakeSource(ProviderManager):
    """Metadata remains real; inference and session access are entirely fake."""

    def __init__(self, directory):
        super().__init__(ModelManager(directory))
        self.fake = StructuredProvider()
        self.closed = False

    def get(self, provider_id):
        self.fake.provider_id = provider_id
        return self.fake

    def close(self):
        self.closed = True


class SilentPlayer:
    def play(self, path):
        pass

    def stop(self):
        pass


@pytest.fixture(scope="module")
def native_window(tmp_path_factory):
    # The desktop has one root/interpreter for its lifetime.
    app = gui.TTSDesktopApp(FakeSource(tmp_path_factory.mktemp("fake-models")))
    app._player = SilentPlayer()
    yield app
    app.destroy()


@pytest.fixture
def window(native_window, monkeypatch):
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *args: None)
    errors = []
    monkeypatch.setattr(
        gui.messagebox, "showerror", lambda *args: errors.append(args[-1])
    )
    native_window._test_errors = errors
    app = native_window
    app._provider_var.set(app._choices["edge"].display_name)
    app._provider_changed()
    app._worker = None
    app._operation_kind = ""
    app._set_busy(False)
    app.geometry("1024x768")
    app.update()
    yield app
    if app._worker is not None:
        app._cancellation_token.cancel()
        app._worker.join(5)
        assert not app._worker.is_alive()
    app.structured.pending_role = False
    app.structured.pending_segment = False
    app.structured.dirty = False


def pump(app, timeout=5):
    deadline = time.monotonic() + timeout
    while (
        app._worker is not None
        and app._worker.is_alive()
        and time.monotonic() < deadline
    ):
        app.update()
        time.sleep(0.01)
    app.update()
    app._drain_queue()
    assert app._worker is None or not app._worker.is_alive()


def sample(app):
    app.structured.set_document(load_document(Path("docs/tts-sample.json")))
    app._mode_tabs.select(app.structured)
    app.structured.roles.selection_set(app.structured.document.speakers[0].id)
    app.structured.segments.selection_set("0")
    app.update()
    return app.structured


def test_sample_role_segment_forms_and_extension_roundtrip(window, tmp_path):
    view = sample(window)
    assert len(view.roles.get_children()) == 3
    assert len(view.segments.get_children()) == 26
    assert len(view.speaker_box["values"]) == 3
    assert "84s explicit silence" in view._summary.get()
    assert "final 30s" in view._summary.get()
    data = view.document.to_dict()
    data["extension"] = {"retained": True}
    view.set_document(view.document.with_data(data))
    view.role_voice.set("custom-edge-id")
    assert view.apply_role()
    assert view.preflight().assignments[0].voice_id == "custom-edge-id"
    view.segments.selection_set("25")
    window.update()
    view.segment_pause.set("29.5")
    assert view.apply_segment()
    target = tmp_path / "saved.json"
    from ttsapp.conversation_document import save_document_as

    save_document_as(view.document, target)
    reopened = load_document(target)
    assert reopened.segments[-1].pause_after_seconds == 29.5
    assert reopened.to_dict()["extension"] == {"retained": True}


@pytest.mark.parametrize("count", [1, 3, 20, 1000])
def test_large_role_navigation_and_resize(window, count):
    view = window.structured
    doc = parse_document_data(
        {
            "speakers": [
                {"id": f"role-{i}", "role": "Long label " * 8 + str(i)}
                for i in range(count)
            ],
            "segments": [{"speaker": "role-0", "text": "Only dialogue."}],
        }
    )
    view.set_document(doc)
    window._mode_tabs.select(view)
    window.geometry("512x384")
    window.update()
    assert len(view.roles.get_children()) == count
    assert len(view.speaker_box["values"]) == count
    view.roles.selection_set(f"role-{count - 1}")
    view.roles.see(f"role-{count - 1}")
    view.roles.focus_force()
    window.update()
    assert view.roles.focus_get() == view.roles
    assert window.generate_button.winfo_ismapped()
    assert window._cancel_button.winfo_ismapped()
    assert (
        sum(isinstance(child, gui.ttk.Combobox) for child in view.winfo_children()) < 10
    )


def test_provider_restore_filter_and_preview_dialogue_settings(window, monkeypatch):
    view = sample(window)
    first = view.document.speakers[0].id
    view.role_voice.set("custom")
    assert view.apply_role()
    window._provider_var.set(window._choices["kokoro"].display_name)
    window._provider_changed()
    view.role_voice.set("af_heart")
    assert view.apply_role()
    window._provider_var.set(window._choices["edge"].display_name)
    window._provider_changed()
    window._voice_search_var.set("nothing-matches")
    assert view.preflight().assignments[0].voice_id == "custom"
    assert view.roles.selection()[0] == first
    calls = []

    async def preview(provider, voice, text, speed, token):
        calls.append((provider, voice, text, speed, threading.current_thread()))
        return Path("fake.wav")

    monkeypatch.setattr(window._preview_service, "generate", preview)
    window._preview_structured()
    pump(window)
    assert calls[0][1] == "custom"
    assert calls[0][2] == view.document.segments[0].text
    assert calls[0][4] != threading.current_thread()


def test_failed_and_stale_import_preserve_document(window, tmp_path, monkeypatch):
    view = sample(window)
    before = view.document
    view.role_voice.set("manual")
    assert view.apply_role()
    bad = tmp_path / "bad.json"
    bad.write_text("{broken", encoding="utf-8")
    window._run_import(bad, window._preview_revision, window._cancellation_token)
    window._drain_queue()
    assert view.document is before or view.document.document_id == before.document_id
    assert view.preflight().assignments[0].voice_id == "manual"
    revision = window._preview_revision
    window._run_import(
        Path("docs/tts-sample.json"), revision, window._cancellation_token
    )
    window._invalidate_preview()
    window._drain_queue()
    assert view.preflight().assignments[0].voice_id == "manual"
    assert view.dirty


def test_generation_snapshot_and_stale_completion(window, monkeypatch, tmp_path):
    view = sample(window)
    window._output_path_var.set(str(tmp_path / "output.wav"))
    window._format_var.set("WAV")
    started = threading.Event()
    finish = threading.Event()
    snapshots = []

    async def generate(**kwargs):
        snapshots.append(kwargs)
        started.set()
        assert finish.wait(3)
        return kwargs["final_audio"]

    monkeypatch.setattr(gui, "generate_conversation", generate)
    window._generate_structured()
    assert started.wait(3)
    old = snapshots[0]["document"]
    view.role_voice.set("new-custom")
    assert view.apply_role()
    finish.set()
    pump(window)
    assert old.document_id == view.document.document_id
    assert old.revision < view.document.revision
    assert snapshots[0]["voice_assignments"] != view.mappings.selections(
        view.document, "edge"
    )
    assert "newer edits" in window._status_var.get()


def test_pending_edits_not_discarded_by_filter(window):
    view = sample(window)
    view.dialogue.delete("1.0", "end")
    view.dialogue.insert("1.0", "Edited dialogue.")
    window.update()
    assert view.pending
    window._voice_search_var.set("filtered")
    window.update()
    assert view.dialogue.get("1.0", "end-1c") == "Edited dialogue."
    assert view.pending
    assert view.apply_segment()
    assert view.document.segments[0].text == "Edited dialogue."


def test_actual_windows_environment(window, tmp_path):
    dpi = ctypes.windll.user32.GetDpiForWindow(window.winfo_id())
    report = {
        "window_dpi": dpi,
        "os_scale_percent": dpi / 96 * 100,
        "tk_scaling": window.tk.call("tk", "scaling"),
        "screen": [window.winfo_screenwidth(), window.winfo_screenheight()],
        "test_window": [window.winfo_width(), window.winfo_height()],
        "note": "Actual host DPI only; other OS scaling modes are unverified.",
    }
    (tmp_path / "windows-environment.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report))
    assert dpi > 0


def test_project_roundtrip_gui_snapshot_and_preset_keeps_manual(window, tmp_path):
    from ttsapp.project_storage import load_project, save_project

    view = sample(window)
    view.role_voice.set("custom-saved")
    assert view.apply_role()
    view.segments.selection_set("25")
    window.update()
    view.segment_pause.set("29.75")
    assert view.apply_segment()
    snapshot = window._capture_project()
    target = tmp_path / "saved.ttsproject.json"
    save_project(snapshot, target)
    view.role_voice.set("changed")
    assert view.apply_role()
    window._adopt_project(load_project(target))
    assert view.preflight().assignments[0].voice_id == "custom-saved"
    assert view.document.segments[-1].pause_after_seconds == 29.75
    assert not view.dirty
    view.preferences = {
        (
            view.document.speakers[0].role.strip().casefold(),
            "edge",
            "en-US",
        ): "preset-choice"
    }
    # An explicit saved assignment is above an enabled reusable preset.
    assert view.preflight().assignments[0].voice_id == "custom-saved"


def test_stale_preview_result_is_rejected(window, monkeypatch):
    view = sample(window)
    started = threading.Event()
    finish = threading.Event()

    async def preview(provider, voice, text, speed, token):
        started.set()
        assert finish.wait(3)
        return Path("old-preview.wav")

    monkeypatch.setattr(window._preview_service, "generate", preview)
    window._preview_structured()
    assert started.wait(3)
    view.role_voice.set("new-selection")
    finish.set()
    pump(window)
    assert window._last_preview is None
    assert "changed" in window._status_var.get()


def test_native_keyboard_navigation_and_scrollbars(window):
    view = sample(window)
    window.geometry("512x384")
    window.update()
    view.tabs.select(0)
    view.roles.focus_force()
    view.roles.focus(view.document.speakers[0].id)
    view.roles.selection_set(view.document.speakers[0].id)
    view.roles.event_generate("<KeyPress-Down>")
    window.update()
    assert view.roles.selection()[0] == view.document.speakers[1].id
    # Native focus traversal reaches off-screen fields and scrolls them into view.
    view.voice_box.focus_force()
    window.update()
    assert window._scroll_canvas.yview()[0] > 0
    assert window.generate_button.winfo_ismapped()


def test_end_to_end_sample_gui_export_project_and_cli(window, tmp_path):
    import asyncio

    from ttsapp.audio_export import probe_audio
    from ttsapp.cli import argument_parser, generate_from_arguments
    from ttsapp.conversation_document import save_document_as
    from ttsapp.project_storage import load_project, save_project, write_json_atomic
    from ttsapp.providers.base import CancellationToken

    view = sample(window)
    window._provider_manager.fake.requests.clear()
    window._format_var.set("WAV")
    final = tmp_path / "gui.wav"
    window._output_path_var.set(str(final))
    window._generate_structured()
    pump(window, timeout=20)
    assert final.is_file(), window._test_errors
    requests = window._provider_manager.fake.requests
    info = probe_audio(final, CancellationToken())
    assert abs(info.duration_seconds - (84 + len(requests) * 100 / 16000)) < 0.01
    view.role_voice.set("custom-e2e")
    assert view.apply_role()
    view.segments.selection_set("25")
    window.update()
    view.segment_pause.set("30.125")
    assert view.apply_segment()
    snapshot = window._capture_project()
    project_file = tmp_path / "e2e.ttsproject.json"
    save_project(snapshot, project_file)
    window._adopt_project(load_project(project_file))
    assert view.document.segments[-1].pause_after_seconds == 30.125
    source = tmp_path / "dialogue.json"
    save_document_as(view.document, source)
    mapping = tmp_path / "voices.json"
    assignments = {
        item.speaker_id: item.voice_id for item in view.preflight().assignments
    }
    write_json_atomic(
        {"schema_version": 1, "provider_id": "edge", "voices": assignments}, mapping
    )
    cli_source = FakeSource(tmp_path / "cli-models")
    output = tmp_path / "cli.wav"
    args = argument_parser().parse_args(
        [
            "--input",
            str(source),
            "--voice-map",
            str(mapping),
            "--output",
            str(output),
        ]
    )
    asyncio.run(generate_from_arguments(args, providers=cli_source))
    assert cli_source.closed
    assert output.is_file()
    metadata_files = list((tmp_path / "audio_parts").glob("job-*/generation.json"))
    timelines = [json.loads(path.read_text()) for path in metadata_files]
    cli_record = next(
        item
        for item in timelines
        if item["segments"][-1]["pause_after_seconds"] == 30.125
    )
    assert cli_record["segments"][0]["voice_id"] == "custom-e2e"
    assert sum(item["pause_after_seconds"] for item in cli_record["segments"]) == 84.125


def test_cancel_fake_generation_keeps_existing_output_and_ui_responsive(
    window, tmp_path, monkeypatch
):
    from ttsapp.audio_export import ExportSettings

    view = sample(window)
    final = tmp_path / "previous.wav"
    final.write_bytes(b"previous")
    started = threading.Event()

    async def delayed(request, output, token):
        started.set()
        await token.wait()
        token.raise_if_cancelled()

    monkeypatch.setattr(window._provider_manager.fake, "synthesize", delayed)
    options = window._read_options()
    from dataclasses import replace

    options = replace(options, export_settings=ExportSettings("wav", overwrite=True))
    doc = view.document
    voices = {item.speaker_id: item.voice_id for item in view.preflight().assignments}
    window._begin_work("generation")
    window._worker = threading.Thread(
        target=window._run_generation,
        args=(
            "",
            tmp_path / "parts",
            final,
            voices,
            options,
            window._cancellation_token,
            doc,
            window._preview_revision,
        ),
    )
    window._worker.start()
    assert started.wait(3)
    beats = []
    window.after(1, lambda: beats.append(True))
    window.update()
    time.sleep(0.01)
    window.update()
    assert beats
    window._cancel_work()
    pump(window)
    assert final.read_bytes() == b"previous"
    assert not window._busy
    record = json.loads(
        next((tmp_path / "parts").glob("job-*/generation.json")).read_text()
    )
    assert record["state"] == "cancelled"


def test_invalid_project_and_unsaved_replace_choices(window, tmp_path, monkeypatch):
    view = sample(window)
    view.role_voice.set("retained-manual")
    assert view.apply_role()
    before = view.document
    invalid = tmp_path / "bad.ttsproject.json"
    invalid.write_text('{"schema_version":2}', encoding="utf-8")
    window._run_import(
        invalid, window._preview_revision, window._cancellation_token, "project"
    )
    window._drain_queue()
    assert view.document is before
    assert view.dirty
    assert view.preflight().assignments[0].voice_id == "retained-manual"
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *args: None)
    assert not window._confirm_replace()
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *args: False)
    assert window._confirm_replace()
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *args: True)
    monkeypatch.setattr(window, "_save_project_as", lambda: False)
    assert not window._confirm_replace()


def test_long_ids_and_same_document_reload_keep_identity(window):
    view = window.structured
    key = "role-" + "x" * 300
    doc = parse_document_data(
        {
            "speakers": [{"id": key, "role": "Long role"}],
            "segments": [{"speaker": key, "text": "Dialogue."}],
        }
    )
    view.set_document(doc)
    window._mode_tabs.select(view)
    window.update()
    view.role_voice.set("long-id-custom")
    assert view.apply_role()
    edited = view.document.with_data(view.document.to_dict())
    view.set_document(edited)
    assert view.preflight().assignments[0].voice_id == "long-id-custom"
    assert key in view.speaker_box["values"][0]


def test_graceful_close_waits_for_fake_worker_cleanup(window, monkeypatch):
    started = threading.Event()
    cleaned = threading.Event()
    destroyed = []

    async def preview(provider, voice, text, speed, token):
        started.set()
        try:
            await token.wait()
            token.raise_if_cancelled()
        finally:
            cleaned.set()

    sample(window)
    monkeypatch.setattr(window._preview_service, "generate", preview)
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *args: False)
    monkeypatch.setattr(window, "destroy", lambda: destroyed.append(True))
    window._preview_structured()
    assert started.wait(3)
    window._on_close()
    deadline = time.monotonic() + 5
    while not destroyed and time.monotonic() < deadline:
        window.update()
        time.sleep(0.01)
    assert cleaned.is_set()
    assert destroyed
    assert window._provider_manager.closed
    window._closing = False
    window._shutdown_started = False
    window._set_busy(False)
    window._operation_kind = ""
    # Resume the poll loop after the intercepted final native destroy.
    window.after(window.POLL_INTERVAL_MS, window._drain_queue)
