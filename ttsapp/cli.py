"""Additive JSON/text CLI; callable legacy main remains in main.py."""

import argparse
import asyncio
import sys
from pathlib import Path

from .audio_export import ExportSettings
from .config import DEFAULT_FINAL_AUDIO, DEFAULT_INPUT_FILE, DEFAULT_OUTPUT_DIR, VOICES
from .conversation_document import load_document
from .parser import ConversationLine, parse_conversation
from .project_storage import read_json_file, validate_voice_map
from .provider_manager import ProviderManager
from .service import ProgressCallback, generate_conversation
from .speaker_mapping import resolve_document


def argument_parser() -> argparse.ArgumentParser:
    """Describe explicit CLI inputs without changing no-argument defaults."""
    parser = argparse.ArgumentParser(
        description="Generate text or structured JSON dialogue."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_FILE)
    parser.add_argument(
        "--input-format", choices=("auto", "text", "json"), default="auto"
    )
    parser.add_argument("--provider", choices=("edge", "piper", "kokoro"))
    parser.add_argument("--voice-map", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_FINAL_AUDIO)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--speed", type=float)
    return parser


async def generate_from_arguments(
    arguments: argparse.Namespace,
    *,
    providers: ProviderManager | None = None,
    on_progress: ProgressCallback = None,
) -> Path:
    """Use the shared parser/resolver/service and always close provider sessions."""
    manager = providers if providers is not None else ProviderManager()
    try:
        input_format = arguments.input_format
        if input_format == "auto":
            input_format = (
                "json" if arguments.input.suffix.lower() == ".json" else "text"
            )
        provider_id = arguments.provider or "edge"
        assignments = None
        document = None
        if input_format == "json":
            document = load_document(arguments.input)
            if arguments.voice_map is not None:
                provider_id, assignments = validate_voice_map(
                    read_json_file(arguments.voice_map),
                    document,
                    arguments.provider,
                )
            choice = next(
                item
                for item in manager.list_choices()
                if item.provider_id == provider_id
            )
            preflight = resolve_document(
                document, choice, current=assignments, job_speed=arguments.speed
            )
            if preflight.errors:
                raise ValueError(
                    "; ".join(
                        f"{item.path}: {item.message}" for item in preflight.errors
                    )
                )
        else:
            if arguments.voice_map is not None:
                raise ValueError("--voice-map requires JSON input.")
            try:
                parse_conversation(arguments.input, VOICES)
            except ValueError as error:
                raise ValueError(
                    "Text input needs configured Speaker: text labels and nonempty dialogue."
                ) from error
        settings = ExportSettings(
            audio_format=arguments.output.suffix.lstrip(".").lower(),
            overwrite=arguments.overwrite,
        )
        provider = manager.get(provider_id)
        kwargs = (
            {"document": document, "voice_assignments": assignments}
            if document
            else {"input_file": arguments.input}
        )
        return await generate_conversation(
            **kwargs,
            provider_id=provider_id,
            provider=provider,
            final_audio=arguments.output,
            output_dir=arguments.output.parent / DEFAULT_OUTPUT_DIR.name,
            speed=arguments.speed,
            export_settings=settings,
            on_progress=on_progress or _print_progress,
        )
    finally:
        manager.close()


def _print_progress(index: int, total: int, line: ConversationLine) -> None:
    print(f"[{index}/{total}] Created segment for {line.speaker}")


def run_cli(argv: list[str] | None = None) -> int:
    """Return actionable errors without dumping private dialogue or tracebacks."""
    arguments = argument_parser().parse_args(argv)
    try:
        result = asyncio.run(generate_from_arguments(arguments))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("Cancelled; cleanup completed.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Final audio created: {result}")
    return 0
