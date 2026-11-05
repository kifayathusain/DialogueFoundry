"""Render the public Director fixtures with existing local Kokoro assets."""

import argparse
import asyncio
import json
import logging
import socket
from pathlib import Path

from ttsapp.audio_export import probe_audio
from ttsapp.director import (
    PhoneScope,
    SceneSettings,
    TimingSettings,
    bind_cast,
    edit_file,
    manual_plan,
    scan_folder,
)
from ttsapp.director_runner import render_file, run_batch, save_report
from ttsapp.models.manager import ModelManager
from ttsapp.provider_manager import ProviderManager
from ttsapp.providers.base import CancellationToken


def _deny_network(*args: object, **kwargs: object) -> None:
    raise RuntimeError("Offline acceptance forbids external network access.")


async def acceptance(model_directory: Path, output: Path) -> dict:
    """Exercise conflict, local casting, phone scope, invalid file and real media."""
    providers = ProviderManager(ModelManager(model_directory))
    token = CancellationToken()
    source = Path("examples/audio_director/Lessons").resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        choice = next(
            choice
            for choice in providers.list_choices()
            if choice.provider_id == "kokoro"
        )
        plan = manual_plan(scan_folder(source), source, output, choice)
        plan = bind_cast(
            plan,
            (("02_discussion.json", "alex"), ("03_telephone_interview.json", "alex")),
            "bm_george",
        )
        for item in plan.files:
            if item.source.document:
                plan = edit_file(
                    plan, item.source.file_id, timing=TimingSettings("natural")
                )
        plan = edit_file(
            plan,
            "03_telephone_interview.json",
            scene=SceneSettings((PhoneScope("guest", 2, 4),)),
        )
        # The sentinel is created only inside this explicitly selected acceptance
        # directory and must survive preflight. Rendering uses a renamed file.
        conflict = output / "01_narration.mp3"
        if conflict.exists():
            raise ValueError("Use a fresh acceptance output folder.")
        conflict.write_bytes(b"existing destination must be retained")
        from ttsapp.director import preflight

        conflicts = preflight(plan, providers.list_choices())
        assert conflicts["01_narration.json"]
        plan = edit_file(
            plan, "01_narration.json", destination_name="01_narration-reviewed.mp3"
        )
        # Prohibit Python network resolution/connections after loop initialization.
        # Local inference uses verified weights, phonemizers and generated effects.
        socket.create_connection = _deny_network
        socket.getaddrinfo = _deny_network
        results = await run_batch(plan, providers, token)
        assert [item.state for item in results] == [
            "completed",
            "completed",
            "completed",
            "failed",
        ], results
        assert conflict.read_bytes() == b"existing destination must be retained"
        telephone = next(
            item for item in plan.files if "telephone" in item.source.file_id
        )
        sample = output / "telephone-directed-exchange.wav"
        await render_file(
            plan, telephone, providers, token, preview="directed", preview_output=sample
        )
        media = {}
        for result in results:
            if result.state == "completed":
                info = probe_audio(Path(result.output), token)
                media[result.file_id] = {
                    "codec": info.codec,
                    "seconds": info.duration_seconds,
                }
        report = save_report(plan, results, output / "acceptance-report.json")
        return {
            "results": [item.state for item in results],
            "media": media,
            "listening_sample": str(sample),
            "full_telephone_with_final_pause": str(output / telephone.destination_name),
            "report": str(report),
            "network_guard": "Python DNS and connection helpers denied during synthesis",
            "human_listening": "Pending; no listening judgment is inferred from media validation.",
        }
    finally:
        providers.close()


def main() -> int:
    """Use installed models only; no download, benchmark or exhaustive voice run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = asyncio.run(acceptance(args.model_directory, args.output.resolve()))
    logging.info("%s", json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
