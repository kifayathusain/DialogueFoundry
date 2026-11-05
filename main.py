"""CLI entry point for the Windows TTS app.

Reads a ``Speaker: text`` conversation script, synthesizes each line with
Microsoft Edge TTS, and combines the resulting segments into a single audio
file with FFmpeg. The actual pipeline lives in :mod:`ttsapp.service` so a
future desktop UI can reuse it without going through this CLI.
"""

import asyncio
import sys

from ttsapp.config import (
    DEFAULT_FINAL_AUDIO,
    DEFAULT_INPUT_FILE,
    DEFAULT_OUTPUT_DIR,
    VOICES,
)
from ttsapp.parser import ConversationLine
from ttsapp.service import generate_conversation


def _print_progress(index: int, total: int, line: ConversationLine) -> None:
    print(f"[{index}/{total}] Created: line_{index:03d}.mp3 ({line.speaker})")


async def main() -> None:
    final_audio = await generate_conversation(
        input_file=DEFAULT_INPUT_FILE,
        output_dir=DEFAULT_OUTPUT_DIR,
        final_audio=DEFAULT_FINAL_AUDIO,
        voices=VOICES,
        on_progress=_print_progress,
    )

    print()
    print(f"Final audio created: {final_audio}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        asyncio.run(main())
    else:
        from ttsapp.cli import run_cli

        raise SystemExit(run_cli())
