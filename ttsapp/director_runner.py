"""Batch execution, multi-turn audition and privacy-safe run reports."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Protocol

from .audio_export import ExportSettings
from .director import (
    BatchPlan,
    FilePlan,
    plan_settings,
    preflight,
    resolved_document,
    treatments,
)
from .project_storage import write_json_atomic
from .provider_manager import ProviderChoice
from .providers.base import CancellationToken, SynthesisRequest, TTSProvider
from .service import generate_conversation
from .speaker_mapping import resolve_document


class DirectorProviders(Protocol):
    """ProviderManager-compatible dependency; future providers need no UI changes."""

    def list_choices(self) -> tuple[ProviderChoice, ...]: ...

    def get(self, provider_id: str) -> TTSProvider: ...


@dataclass(frozen=True)
class FileResult:
    """One file boundary state without dialogue or raw provider responses."""

    file_id: str
    state: str
    output: str = ""
    diagnostic: str = ""


@dataclass(frozen=True)
class BatchEvent:
    """Queued UI/agent progress, independently useful without a desktop."""

    file_id: str
    state: str
    completed: int
    total: int
    turn: int = 0
    turns: int = 0


def verify_assets(
    plan: BatchPlan, providers: DirectorProviders, token: CancellationToken
) -> dict[str, tuple[str, ...]]:
    """Verify required models off the UI thread without synthesizing or downloading."""
    choices = providers.list_choices()
    errors = preflight(plan, choices, check_sources=True)
    for item in plan.files:
        token.raise_if_cancelled()
        file_id = item.source.file_id
        if item.skipped or errors[file_id]:
            continue
        try:
            provider = providers.get(item.provider_id)
            capabilities = provider.get_capabilities()
            if plan.offline and capabilities.online:
                raise ValueError("Offline mode requires a local provider.")
            choice = next(
                choice for choice in choices if choice.provider_id == item.provider_id
            )
            resolved = resolve_document(
                resolved_document(item),
                choice,
                current=dict(item.cast),
                job_speed=item.speed,
            )
            checked = set()
            native = "wav" if "wav" in capabilities.audio_formats else "mp3"
            for segment in resolved.segments:
                token.raise_if_cancelled()
                identity = segment.voice_id, segment.speed
                if identity in checked:
                    continue
                provider.validate_configuration(
                    SynthesisRequest(
                        "Voice readiness check.",
                        segment.voice_id,
                        audio_format=native,
                        speed=segment.speed,
                    )
                )
                checked.add(identity)
        except (OSError, ValueError, RuntimeError):
            errors[file_id] = (
                "Required voice assets are missing or invalid. Open Model library to install/verify this voice; no substitution or download was performed.",
            )
    return errors


async def render_file(
    plan: BatchPlan,
    item: FilePlan,
    providers: DirectorProviders,
    token: CancellationToken,
    *,
    progress: Callable[[int, int], None] | None = None,
    preview: str | None = None,
    preview_output: Path | None = None,
) -> Path:
    """Use the structured service and validated exporter for every render mode."""
    token.raise_if_cancelled()
    document = resolved_document(item)
    effects = treatments(item)
    provider = providers.get(item.provider_id)
    if plan.offline and provider.get_capabilities().online:
        raise ValueError("Fully offline mode requires a local synthesis provider.")
    destination = plan.output_folder / item.destination_name
    settings = ExportSettings(audio_format=plan.audio_format, overwrite=item.overwrite)
    if preview is not None:
        if preview not in {"original", "directed"} or preview_output is None:
            raise ValueError("Select Original or Directed audition and a cache file.")
        start, end = excerpt_range(item)
        data = document.to_dict()
        if preview == "original":
            data = item.source.document.to_dict()
            effects = {}
        data["segments"] = data["segments"][start:end]
        document = document.with_data(data)
        effects = {
            index - start: value
            for index, value in effects.items()
            if start < index <= end
        }
        destination = preview_output
        settings = ExportSettings(audio_format="wav", overwrite=True)
    # Chunk jobs and intermediate PCM are private, bounded to this file lifetime.
    with tempfile.TemporaryDirectory(prefix="tts-director-") as work:
        return await generate_conversation(
            document=document,
            voice_assignments=dict(item.cast),
            provider_id=item.provider_id,
            provider=provider,
            speed=item.speed,
            output_dir=Path(work),
            final_audio=destination,
            export_settings=settings,
            cancellation_token=token,
            segment_treatments=effects,
            on_progress=(lambda index, total, line: progress(index, total))
            if progress
            else None,
        )


def excerpt_range(item: FilePlan) -> tuple[int, int]:
    """Choose the same adjacent exchange for Original and Directed auditions."""
    document = item.source.document
    if document is None:
        raise ValueError("A valid conversation is required for audition.")
    segments = document.segments
    for index, segment in enumerate(segments):
        if any(
            scope.speaker == segment.speaker and scope.start <= index + 1 <= scope.end
            for scope in item.scene.phone
        ):
            if index and segments[index - 1].speaker != segment.speaker:
                return index - 1, index + 1
            if index + 1 < len(segments):
                return index, index + 2
    for index in range(len(segments) - 1):
        if segments[index].speaker != segments[index + 1].speaker:
            return index, index + 2
    return 0, min(2, len(segments))


async def run_batch(
    plan: BatchPlan,
    providers: DirectorProviders,
    token: CancellationToken,
    *,
    on_event: Callable[[BatchEvent], None] | None = None,
    previous: tuple[FileResult, ...] = (),
    retry_ids: frozenset[str] | None = None,
) -> tuple[FileResult, ...]:
    """Execute at file boundaries, retaining completed outputs and retry settings."""
    if retry_ids is not None:
        eligible = {
            item.file_id for item in previous if item.state in {"failed", "cancelled"}
        }
        if not retry_ids <= eligible:
            raise ValueError("Retry only selected failed or cancelled files.")
    validation = preflight(plan, providers.list_choices(), check_sources=True)
    results = {item.file_id: item for item in previous}
    total = sum(
        not item.skipped and (retry_ids is None or item.source.file_id in retry_ids)
        for item in plan.files
    )
    completed = 0
    stopped = False
    for item in plan.files:
        file_id = item.source.file_id
        if retry_ids is not None and file_id not in retry_ids:
            continue
        if item.skipped:
            results[file_id] = FileResult(file_id, "skipped")
            continue
        if token.is_cancelled or stopped:
            results[file_id] = FileResult(
                file_id,
                "cancelled",
                diagnostic="Run cancelled or stopped before this file.",
            )
        elif validation[file_id]:
            results[file_id] = FileResult(
                file_id,
                "failed",
                diagnostic=(
                    "Unresolved direction review issues; inspect the active plan."
                    if item.issues
                    else "; ".join(validation[file_id])
                ),
            )
            stopped = plan.failure_policy == "stop"
        else:
            if on_event:
                on_event(BatchEvent(file_id, "running", completed, total))
            boundary_error = ""
            try:
                # Revalidate immediately before this boundary, after earlier files ran.
                fresh = preflight(
                    replace(plan, files=(item,)),
                    providers.list_choices(),
                    check_sources=True,
                )
                if fresh[file_id]:
                    boundary_error = "; ".join(fresh[file_id])
                    raise ValueError(boundary_error)
                output = await render_file(
                    plan,
                    item,
                    providers,
                    token,
                    progress=(
                        lambda turn, turns, current=file_id, count=completed: on_event(
                            BatchEvent(current, "running", count, total, turn, turns)
                        )
                    )
                    if on_event
                    else None,
                )
                results[file_id] = FileResult(file_id, "completed", str(output))
            except asyncio.CancelledError:
                token.cancel()
                results[file_id] = FileResult(
                    file_id,
                    "cancelled",
                    diagnostic="Cancelled; temporary audio cleaned. Completed outputs retained.",
                )
            except Exception as error:
                # Provider failures may echo text or remote payloads; never persist them.
                diagnostic = f"{type(error).__name__}: check voice/model availability in Model library, output permissions and FFmpeg; then retry."
                if boundary_error:
                    diagnostic = boundary_error
                results[file_id] = FileResult(file_id, "failed", diagnostic=diagnostic)
                stopped = plan.failure_policy == "stop"
        completed += 1
        if on_event:
            on_event(BatchEvent(file_id, results[file_id].state, completed, total))
    return tuple(
        results[item.source.file_id]
        for item in plan.files
        if item.source.file_id in results
    )


def save_report(
    plan: BatchPlan, results: tuple[FileResult, ...], destination: Path
) -> Path:
    """Publish a data-only report; no raw prompts, dialogue or credentials."""
    return write_json_atomic(
        {
            "kind": "audio_director_report",
            "schema_version": 1,
            "revision": plan.revision,
            "results": [asdict(item) for item in results],
            "settings": {
                item.source.file_id: {
                    **plan_settings(item),
                    "source_sha256": item.source.fingerprint,
                    "resolved_after_pauses": item.resolved_after_pauses,
                    "destination": item.destination_name,
                }
                for item in plan.files
            },
        },
        destination,
    )
