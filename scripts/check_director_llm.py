"""Reproducible connection test; no conversation data is sent."""

import argparse
import asyncio
import logging

from ttsapp.director_planner import LLMConnection, LocalLLMPlanner
from ttsapp.providers.base import CancellationToken


def main() -> int:
    """Check an explicitly configured JSON-mode chat-completions server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--allow-cloud", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    planner = LocalLLMPlanner(
        LLMConnection(args.endpoint, args.model, args.allow_cloud)
    )
    try:
        result = asyncio.run(
            planner.test_connection(CancellationToken(), offline=not args.allow_cloud)
        )
    except (OSError, ValueError) as error:
        logging.error("%s", error)
        return 1
    logging.info("%s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
