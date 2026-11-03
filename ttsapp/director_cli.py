"""Headless discovery, review and rendering for Audio Director."""

import argparse
import asyncio
import json
import shutil
import sys
from contextlib import redirect_stdout
from dataclasses import asdict, replace
from importlib.util import find_spec
from pathlib import Path

from .audio_export import ExportSettings
from .conversation_document import MAX_INPUT_BYTES, parse_document_text
from .director import (
    BatchPlan,
    FilePlan,
    ScanResult,
    SourceFile,
    fingerprint,
    manual_plan,
    plan_settings,
    resolved_document,
    treatments,
)
from .director_planner import parse_settings
from .director_runner import render_file, verify_assets
from .models.manager import InstallationState, ModelManager
from .provider_manager import ProviderChoice, ProviderManager
from .providers.base import CancellationToken
from .speaker_mapping import resolve_document

RUNTIMES = {"edge": "edge_tts", "piper": "piper", "kokoro": "kokoro_onnx"}


def discover(manager: ProviderManager) -> dict:
    """Report catalog metadata separately from local model integrity."""
    return {
        "runtime_packages_present": {
            name: find_spec(package) is not None for name, package in RUNTIMES.items()
        },
        "runtime_remedy": "Install the selected provider requirements in the active Python environment.",
        "media_remedy": "Install FFmpeg with ffprobe and add its bin directory to PATH.",
        "model_directory": str(manager.models.directory.resolve()),
        "export_formats": ["wav", "mp3", "m4a"],
        "providers": [asdict(choice) for choice in manager.list_choices()],
        "assets": {
            model.model_id: manager.models.status(model.model_id).value
            for model in manager.models.list_models()
        },
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


def resolve_voices(
    item: FilePlan,
    choice: ProviderChoice,
    available: ProviderChoice,
    assigned: dict[str, str],
    raw: dict,
) -> tuple[dict, dict]:
    """Apply locale preferences only to unlocked voices and report each match."""
    document = item.source.document
    assert document is not None
    cast = dict(item.cast)
    cast.update(assigned)
    catalog = {v.voice_id: v for v in choice.voices}
    locale = raw.get("locale")
    required = raw.get("required", False)
    if (
        type(required) is not bool
        or (locale is not None and not isinstance(locale, str))
        or (required and not locale)
    ):
        raise ValueError("Specify a locale string and boolean required flag.")
    if assigned.keys() - {s.id for s in document.speakers}:
        raise ValueError("Unknown speaker assignment.")
    reports = {}
    for speaker in document.speakers:
        if cast[speaker.id] not in catalog:
            raise ValueError(
                f"Unknown {choice.provider_id} voice for {speaker.id}: {cast[speaker.id]}"
            )
        voice = catalog[cast[speaker.id]]
        if locale:
            matches = [
                v
                for v in available.voices
                if v.language.casefold() == locale.casefold()
            ]
            if (
                matches
                and speaker.id not in assigned
                and not speaker.voice_defaults.get(choice.provider_id)
            ):
                voice = min(
                    matches,
                    key=lambda v: (
                        v.gender != speaker.gender,
                        v.voice_id != voice.voice_id,
                        v.voice_id in cast.values(),
                        v.voice_id,
                    ),
                )
                cast[speaker.id] = voice.voice_id
            matched = voice.language.casefold() == locale.casefold()
            reports[speaker.id] = {
                "requested": locale,
                "language": voice.language,
                "matched": matched,
            }
            if required and not matched:
                raise ValueError(
                    f"Required locale {locale} unavailable for {speaker.id}."
                )
    return cast, reports


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
        or raw.keys() - {"version", "settings", "locale", "required", "export"}
        or type(raw.get("version")) is not int
        or raw.get("version") != 1
    ):
        raise ValueError("Expected version 1 Director direction.")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise ValueError(f"Install FFmpeg and add {tool} to PATH.")
    changes = parse_settings(raw["settings"])
    choices = {c.provider_id: c for c in manager.list_choices()}
    provider_id = changes["provider_id"]
    if provider_id not in choices:
        raise ValueError(f"Unknown provider {provider_id}. Run director discover.")
    choice = choices[provider_id]
    package = RUNTIMES.get(provider_id)
    if package and find_spec(package) is None:
        raise ValueError(
            f"Install {package} in this Python environment before rendering."
        )
    available = choice
    if choice.provider_id == "piper":
        installed = {
            model.model_id
            for model in manager.models.list_models()
            if model.provider_id == "piper"
            and manager.models.status(model.model_id) == InstallationState.INSTALLED
        }
        available = replace(
            choice, voices=tuple(v for v in choice.voices if v.model_id in installed)
        )
        if not available.voices:
            raise ValueError("Install and verify a Piper model in Model library.")
    entry = SourceFile(source.name, source, fingerprint(data), document)
    plan = manual_plan(
        ScanResult((entry,), ()),
        source.parent,
        output.parent,
        available,
        audio_format=output.suffix[1:].lower(),
        offline=not choice.online,
    )
    item = plan.files[0]
    cast, reports = resolve_voices(
        item, choice, available, dict(changes.pop("cast")), raw
    )
    item = replace(
        item,
        **changes,
        cast=tuple(cast.items()),
        destination_name=output.name,
        overwrite=request["overwrite"],
    )
    plan = replace(plan, files=(item,))
    errors = verify_assets(plan, manager, CancellationToken())[source.name]
    if errors:
        raise ValueError(" ".join(errors))
    resolved = resolve_document(
        resolved_document(item), choice, current=cast, job_speed=item.speed
    )
    effects = treatments(item)
    turns = [
        {
            "speaker": s.speaker_id,
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
        preferences=reports,
        turns=turns,
    )
    return plan, item, snapshot


def run_cli(argv: list[str]) -> int:
    """Execute a Director command and emit one JSON result."""
    parser = argparse.ArgumentParser(prog="main.py director")
    parser.add_argument("--model-directory", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("discover")
    validate = commands.add_parser("validate")
    for name in ("input", "direction", "output", "plan"):
        validate.add_argument("--" + name, type=Path, required=True)
    validate.add_argument("--overwrite", action="store_true")
    commands.add_parser("render").add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    manager = ProviderManager(ModelManager(args.model_directory))
    try:
        if args.command == "discover":
            result = discover(manager)
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
