"""DirectorX — autonomous local cinematic video factory."""
from __future__ import annotations

import argparse
import logging
import sys

import config
from director import load_topics, ollama_reachable
from pipeline import run_topic
from utils import comfyui_reachable, new_client_id


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DirectorX local cinematic video factory")
    parser.add_argument("--dry-run", action="store_true", help="Skip ComfyUI/Ollama GPU path; placeholder clips")
    parser.add_argument("--topics", type=str, default=str(config.TOPICS_FILE), help="Path to topics file")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    log = logging.getLogger("directorx")

    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from pathlib import Path

    topics_path = Path(args.topics)
    jobs = load_topics(topics_path)
    if not jobs:
        log.error("No topics found in %s", topics_path)
        return 1

    if not args.dry_run:
        if not ollama_reachable():
            log.error("Ollama not reachable at localhost:11434. Start it, then retry.")
            return 1
        if not comfyui_reachable():
            log.error(
                "ComfyUI not reachable at %s. Launch ComfyUI, export workflow_api.json, then retry.",
                config.COMFYUI_HOST,
            )
            return 1
        if not config.WORKFLOW_API.exists():
            log.error(
                "Missing workflow_api.json. Copy from workflows/ after exporting ComfyUI API format. "
                "See workflows/README.md"
            )
            return 1

    log.info("Loaded %s topic(s). dry_run=%s", len(jobs), args.dry_run)
    client_id = new_client_id()
    ok = 0
    for i, job in enumerate(jobs, start=1):
        log.info("======== [%s/%s] %s ========", i, len(jobs), job.topic)
        result = run_topic(job, dry_run=args.dry_run, client_id=client_id)
        if result:
            ok += 1
            log.info("OK → %s", result)
        else:
            log.error("FAILED → %s (see %s)", job.topic, config.ERROR_LOG)

    log.info("Done. %s/%s succeeded. Outputs: %s", ok, len(jobs), config.OUTPUT_DIR)
    return 0 if ok == len(jobs) else 2


if __name__ == "__main__":
    sys.exit(main())
