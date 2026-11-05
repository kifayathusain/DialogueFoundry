"""Headless discovery, review and rendering for Audio Director."""

import argparse
import asyncio
import json
import shutil
import sys
from contextlib import redirect_stdout
from dataclasses import asdict
from importlib.util import find_spec
from pathlib import Path

from .audio_export import ExportSettings
from .conversation_document import MAX_INPUT_BYTES, parse_document_text
from .director import (
    BatchPlan,
    FilePlan,
    SourceFile,
    fingerprint,
    plan_settings,
    resolved_document,
    treatments,
)
from .director_casting import parse_voice_assignments, resolve_cli_cast
from .director_planner import parse_settings
from .director_runner import render_file, verify_assets
from .models.english_catalog import piper_english_catalog
from .models.manager import InstallationState, ModelManager
from .provider_manager import ProviderChoice, ProviderManager
from .providers.base import CancellationToken, VoiceMetadata
from .speaker_mapping import resolve_document

RUNTIMES = {"edge": "edge_tts", "piper": "piper", "kokoro": "kokoro_onnx"}


def discover(manager: ProviderManager, *, offline: bool = False) -> dict:
    """Report catalog metadata separately from local model integrity."""
    runtimes = {
        name: find_spec(package) is not None for name, package in RUNTIMES.items()
    }
    assets = {
        model.model_id: manager.models.status(model.model_id).value
        for model in manager.models.list_models()
    }
    piper_speakers = {
        speaker.voice_id: speaker.speaker_id
        for entry in piper_english_catalog()
        for speaker in entry.speakers
    }
    providers = []
    for choice in manager.list_choices():
        if offline and choice.online:
            continue
        voices = []
        for voice in choice.voices:
            state = "online_unchecked"
            if not choice.online:
                state = "local_assets_unavailable"
                if assets.get(voice.model_id) == InstallationState.INSTALLED.value:
                    state = "local_assets_verified"
            voices.append(
                {
                    **asdict(voice),
                    "provider": choice.provider_id,
                    "catalog_locale": voice.language,
                    "speaker_id": piper_speakers.get(voice.voice_id)
                    if choice.provider_id == "piper"
                    else None,
                    "readiness": state,
                    "runtime_present": runtimes[choice.provider_id],
                    "synthesis_tested": False,
                }
            )
        providers.append({**asdict(choice), "voices": voices})
    return {
        "runtime_packages_present": runtimes,
        "offline": offline,
        "runtime_remedy": "Install the selected provider requirements in the active Python environment.",
        "media_remedy": "Install FFmpeg with ffprobe and add its bin directory to PATH.",
        "model_directory": str(manager.models.directory.resolve()),
        "export_formats": ["wav", "mp3", "m4a"],
        "providers": providers,
        "assets": assets,
        "catalog_scope": "Pinned Kokoro/Piper catalogs and configured Edge voices; Edge service availability unchecked.",
        "matching_metadata": ["catalog_locale", "gender"],
        "uncatalogued_traits": "Warmth, authority and other descriptive qualities require judgment/listening.",
        "asset_remedy": "Install missing assets using Model library.",
        "online_check": "Catalog only. Network and synthesis untested.",
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "scene_presets": [
            "Clean narration",
            "Natural discussion",
            "Telephone interview",
        ],
        "effects": {
            "phone": "speaker within inclusive one-based turn range",
            "room_level": "all speech",
            "paper": "single turn",
            "chair": "single turn",
        },
    }


def resolve(
    request: dict, manager: ProviderManager
) -> tuple[BatchPlan, FilePlan, dict]:
    """Rebuild a reviewed snapshot from bounded source and versioned direction."""
    source, direction, output = (
        Path(request[key]) for key in ("input", "direction", "output")
    )
    with source.open("rb") as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    document = parse_document_text(data)
    direction_bytes = direction.read_bytes()
    raw = json.loads(direction_bytes.decode("utf-8-sig"))
    if (
        not isinstance(raw, dict)
        or raw.keys()
        - {
            "version",
            "settings",
            "locale",
            "required",
            "export",
            "offline",
            "speaker_preferences",
            "casting_notes",
        }
        or type(raw.get("version")) is not int
        or raw.get("version") != 1
    ):
        raise ValueError("Expected version 1 Director direction.")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise ValueError(f"Install FFmpeg and add {tool} to PATH.")
    settings = raw["settings"]
    if not isinstance(settings, dict):
        raise ValueError("Settings must be an object.")
    assigned, overrides = parse_voice_assignments(settings.get("voices"))
    changes = parse_settings({**settings, "voices": assigned})
    changes.pop("cast")
    choices = manager.list_choices()
    providers = {c.provider_id: c for c in choices}
    provider_id = changes["provider_id"]
    if provider_id not in providers:
        raise ValueError(f"Unknown provider {provider_id}. Run director discover.")
    offline = raw.get("offline", not providers[provider_id].online)
    if type(offline) is not bool:
        raise ValueError("Offline must be a boolean.")
    statuses = {}

    def ready(choice: ProviderChoice, voice: VoiceMetadata) -> bool:
        package = RUNTIMES.get(choice.provider_id)
        if package and find_spec(package) is None:
            return False
        if voice.model_id:
            if voice.model_id not in statuses:
                statuses[voice.model_id] = manager.models.status(voice.model_id)
            return statuses[voice.model_id] == InstallationState.INSTALLED
        return True

    cast, reports = resolve_cli_cast(
        document, choices, provider_id, assigned, overrides, raw, ready
    )
    piper_speakers = {
        speaker.voice_id: speaker.speaker_id
        for entry in piper_english_catalog()
        for speaker in entry.speakers
    }
    for report in reports.values():
        report["speaker_id"] = (
            piper_speakers.get(report["voice"])
            if report["provider"] == "piper"
            else None
        )
    entry = SourceFile(source.name, source, fingerprint(data), document)
    item = FilePlan(
        source=entry,
        **changes,
        cast=tuple(cast.items()),
        speaker_providers=tuple(overrides.items()),
        destination_name=output.name,
        overwrite=request["overwrite"],
    )
    plan = BatchPlan(
        source.parent,
        output.parent,
        (item,),
        audio_format=output.suffix[1:].lower(),
        offline=offline,
    )
    errors = verify_assets(plan, manager, CancellationToken())[source.name]
    if errors:
        raise ValueError(" ".join(errors))
    resolved = resolve_document(
        resolved_document(item),
        providers[provider_id],
        current=cast,
        job_speed=item.speed,
        speaker_choices={
            speaker: providers[overrides.get(speaker, provider_id)] for speaker in cast
        },
    )
    effects = treatments(item)
    turns = [
        {
            "speaker": s.speaker_id,
            "provider": s.provider_id,
            "voice": s.voice_id,
            "speed": s.speed,
            "pause_after_seconds": item.resolved_after_pauses[i - 1],
            "effect": asdict(effects[i]) if i in effects else None,
        }
        for i, s in enumerate(resolved.segments, 1)
    ]
    options = raw.get("export", {})
    if not isinstance(options, dict) or options.keys() - {
        "channels",
        "sample_rate",
        "mp3_bitrate_kbps",
        "normalize",
    }:
        raise ValueError("Invalid export settings.")
    if type(options.get("normalize", False)) is not bool or any(
        type(v) is not int for k, v in options.items() if k != "normalize"
    ):
        raise ValueError(
            "Export requires integer audio settings and boolean normalize."
        )
    if "mp3_bitrate_kbps" in options and plan.audio_format != "mp3":
        raise ValueError("MP3 bitrate requires MP3 output.")
    export = ExportSettings(
        audio_format=plan.audio_format, overwrite=item.overwrite, **options
    )
    snapshot = dict(
        version=1,
        direction_hash=fingerprint(direction_bytes),
        export=asdict(export),
        request=request,
        source_hash=entry.fingerprint,
        overwrite=item.overwrite,
        destination=str(output),
        settings=plan_settings(item),
        offline=offline,
        preferences=reports,
        cast=reports,
        turns=turns,
    )
    return plan, item, snapshot


def run_cli(argv: list[str]) -> int:
    """Execute a Director command and emit one JSON result."""
    parser = argparse.ArgumentParser(prog="main.py director")
    parser.add_argument("--model-directory", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    discovery = commands.add_parser("discover")
    discovery.add_argument("--offline", action="store_true")
    validate = commands.add_parser("validate")
    for name in ("input", "direction", "output", "plan"):
        validate.add_argument("--" + name, type=Path, required=True)
    validate.add_argument("--overwrite", action="store_true")
    commands.add_parser("render").add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    manager = ProviderManager(ModelManager(args.model_directory), retain_sessions=True)
    try:
        if args.command == "discover":
            result = discover(manager, offline=args.offline)
        elif args.command == "validate":
            request = {
                key: str(getattr(args, key).resolve())
                for key in ("input", "direction", "output")
            }
            request["overwrite"] = args.overwrite
            _, _, result = resolve(request, manager)
            with args.plan.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, indent=2)
        else:
            reviewed = json.loads(args.plan.read_text(encoding="utf-8-sig"))
            request = reviewed["request"]
            if type(request["overwrite"]) is not bool:
                raise ValueError("Invalid overwrite setting.")
            plan, item, result = resolve(request, manager)
            if result != reviewed:
                raise ValueError("Stale plan. Validate again before rendering.")
            with redirect_stdout(sys.stderr):
                output = asyncio.run(
                    render_file(
                        plan,
                        item,
                        manager,
                        CancellationToken(),
                        export_settings=ExportSettings(**result["export"]),
                    )
                )
            result["output"] = str(output)
        print(json.dumps(result))
        return 0
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("Cancelled.", file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as error:
        print(f"Director error: {error}", file=sys.stderr)
        return 1
    finally:
        manager.close()
