"""Untrusted plan validation and real HTTP protocol with a local fake server."""

import asyncio
import copy
import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.test_director import Providers, write_source
from ttsapp.director import edit_file, manual_plan, plan_settings, scan_folder
from ttsapp.director_planner import (
    LLMConnection,
    LocalLLMPlanner,
    apply_proposal,
    build_inventory,
    flag_direction_limits,
)
from ttsapp.providers.base import CancellationToken, VoiceMetadata


@pytest.fixture
def planning(tmp_path):
    source = tmp_path / "input"
    write_source(source / "lesson.json")
    providers = Providers()
    choice = replace(
        providers.list_choices()[0],
        voices=providers.list_choices()[0].voices
        + (VoiceMetadata("other", "Other", "en-GB"),),
    )
    plan = manual_plan(scan_folder(source), source, tmp_path / "output", choice)
    proposal = {
        "schema_version": 1,
        "failure_policy": "continue",
        "audio_format": "mp3",
        "files": [
            {"file_id": item.source.file_id, **plan_settings(item), "issues": []}
            for item in plan.files
        ],
    }
    return plan, (choice,), proposal


def test_versioned_plan_and_manual_correction_survive_replanning(planning):
    plan, choices, proposal = planning
    corrected = edit_file(
        plan, "lesson.json", cast=(("host", "other"), ("guest", "voice"))
    )
    directed = apply_proposal(corrected, proposal, choices)
    assert dict(directed.files[0].cast)["host"] == "other"
    assert directed.files[0].issues
    assert directed.files[0].source.document is plan.files[0].source.document


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(schema_version=True),
        lambda data: data.update(command="erase files"),
        lambda data: data["files"][0].update(file_id="../other.json"),
        lambda data: data["files"][0].update(voices={"invented": "voice"}),
        lambda data: data["files"][0].update(
            voices={"host": "unknown", "guest": "voice"}
        ),
        lambda data: data["files"][0].update(speed=1.1),
        lambda data: data["files"][0]["scene"].update(
            cues=[{"segment": 1, "kind": "download https://example.invalid"}]
        ),
        lambda data: data["files"][0]["scene"].update(
            phone=[{"speaker": "guest", "start": 1, "end": 900}]
        ),
        lambda data: data["files"][0]["timing"].update(mode="overlap"),
        lambda data: data["files"][0]["scene"].update(room_level=True),
        lambda data: data["files"][0].update(destination="C:/escape.wav"),
    ],
)
def test_invalid_model_decisions_cannot_trigger_actions(planning, mutation):
    plan, choices, proposal = planning
    changed = copy.deepcopy(proposal)
    mutation(changed)
    with pytest.raises(ValueError):
        apply_proposal(plan, changed, choices)
    assert not plan.output_folder.exists()


def test_inventory_metadata_first_and_excerpts_are_opt_in(planning):
    plan, choices, _ = planning
    metadata = json.dumps(build_inventory(plan, choices))
    assert "First?" not in metadata
    assert "pause_after_seconds" not in metadata
    assert "First?" in json.dumps(build_inventory(plan, choices, include_excerpts=True))


def test_cloud_is_blocked_before_network_even_without_excerpts(planning, monkeypatch):
    plan, choices, _ = planning
    planner = LocalLLMPlanner(LLMConnection("https://example.invalid/v1", "fake"))
    monkeypatch.setattr(
        planner, "_request", lambda *args: pytest.fail("No network allowed")
    )
    with pytest.raises(ValueError, match="local loopback"):
        asyncio.run(
            planner.build("Use British voices", plan, choices, CancellationToken())
        )
    allowed = LocalLLMPlanner(LLMConnection("https://example.invalid/v1", "fake", True))
    monkeypatch.setattr(
        allowed, "_request", lambda *args: pytest.fail("Offline blocks network")
    )
    with pytest.raises(ValueError, match="local loopback"):
        asyncio.run(
            allowed.build("Use British voices", plan, choices, CancellationToken())
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://[",
        "http://127.0.0.1:99999/v1",
        "file:///tmp/model",
        "http://127.0.0.1:0/v1",
    ],
)
def test_invalid_endpoint_is_an_actionable_configuration_error(endpoint):
    connection = LLMConnection(endpoint, "local-model")
    assert isinstance(connection.local, bool)
    with pytest.raises(ValueError):
        connection.validate(offline=True)


def test_unsupported_overlap_requires_explicit_sequential_review(planning):
    plan, _, _ = planning
    directed = flag_direction_limits(
        plan, "Make the voices overlap and sound reassuring."
    )
    assert any("sequential" in issue for issue in directed.files[0].issues)
    assert any("delivery" in issue for issue in directed.files[0].issues)


@pytest.mark.integration
def test_cancel_interrupts_a_stalled_local_llm_request():
    accepted = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            accepted.set()
            release.wait(4)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    token = CancellationToken()

    def cancel():
        assert accepted.wait(2)
        token.cancel()

    canceller = threading.Thread(target=cancel, daemon=True)
    canceller.start()
    planner = LocalLLMPlanner(
        LLMConnection(
            f"http://127.0.0.1:{server.server_port}/v1", "fake", timeout_seconds=3
        )
    )
    try:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(planner.test_connection(token))
    finally:
        release.set()
        server.shutdown()
        worker.join()
        canceller.join()
        server.server_close()


@pytest.mark.integration
def test_adapter_posts_actual_protocol_and_validates_json(planning):
    plan, choices, proposal = planning
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, payload))
            test = "connected" in payload["messages"][0]["content"]
            content = json.dumps({"connected": True} if test else proposal)
            response = json.dumps(
                {"choices": [{"message": {"content": content}}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/v1"
        planner = LocalLLMPlanner(LLMConnection(endpoint, "fake-local"))
        assert "Connected" in asyncio.run(planner.test_connection(CancellationToken()))
        directed = asyncio.run(
            planner.build("Use British voices", plan, choices, CancellationToken())
        )
        assert directed.files[0].cast == plan.files[0].cast
        assert requests[0][0] == "/v1/chat/completions"
        assert requests[1][1]["response_format"] == {"type": "json_object"}
        assert "First?" not in json.dumps(requests)
    finally:
        server.shutdown()
        worker.join()
        server.server_close()
