"""DirectorX — autonomous local cinematic video factory."""
from __future__ import annotations

import argparse
import logging
import sys

import config
from director import load_topics, ollama_reachable
from pipeline import run_topic
from utils import comfyui_reachable, force_ollama_cpu, new_client_id


def _job_needs_ollama(job) -> bool:
    """Love/horror/locked reel/raw topics use locked screenplays — no live Ollama call required."""
    if getattr(job, "director_mode", "story") == "raw":
        return False
    t = (job.topic or "").lower()
    love_keys = ("love", "romance", "romantic", "metro love", "प्यार", "इश्क", "मोहब्बत", "प्रेम", "लव")
    if any(k in t or k in (job.topic or "") for k in love_keys):
        return False
    from director import (
        _is_analog_phone_reel_topic,
        _is_dinner_date_topic,
        _is_music_video_lyric_topic,
        _is_usa_sports_quiz_topic,
        _is_wingsuit_canyon_topic,
    )

    if _is_dinner_date_topic(job.topic or ""):
        return False
    if _is_analog_phone_reel_topic(job.topic or ""):
        return False
    if _is_music_video_lyric_topic(job.topic or ""):
        return False
    if _is_usa_sports_quiz_topic(job.topic or ""):
        return False
    if _is_wingsuit_canyon_topic(job.topic or ""):
        return False
    if "horror" in t or "jumpscare" in t or "jump scare" in t:
        return False
    return True


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
    parser.add_argument(
        "--topic",
        type=str,
        default="",
        help="Single inline topic (overrides --topics file when set)",
    )
    parser.add_argument(
        "--topic-file",
        type=str,
        default="",
        help="Read a single topic from a UTF-8 text file (avoids PowerShell quoting issues)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["story", "raw"],
        default="story",
        help="story=normal 3-act LLM path; raw=100%% LLM-off prompt-driven Reel",
    )
    parser.add_argument(
        "--no-captions",
        action="store_true",
        help="Disable burned text overlays on the final video",
    )
    parser.add_argument("--limit", type=int, default=0, help="Process only first N topics (0 = all)")
    parser.add_argument("--scenes", type=int, default=0, help="Override SCENES_PER_VIDEO for this run (e.g. 3)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    log = logging.getLogger("directorx")
    # Keep the 12GB card free for Comfy — Ollama must not touch CUDA
    force_ollama_cpu()

    if args.scenes and args.scenes > 0:
        config.SCENES_PER_VIDEO = int(args.scenes)
        log.info("Scenes override: SCENES_PER_VIDEO=%s", config.SCENES_PER_VIDEO)
    if args.mode == "raw":
        log.info("Raw mode: LLM fully disabled — prompt/overlay driven Reel")
    if getattr(args, "no_captions", False):
        config.FORCE_NO_CAPTIONS = True
        log.info("Captions disabled (--no-captions)")
    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from pathlib import Path

    from director import parse_topic_line

    topic_text = (args.topic or "").strip()
    topic_file = (getattr(args, "topic_file", None) or "").strip()
    if topic_file:
        tp = Path(topic_file)
        if not tp.exists():
            log.error("Topic file not found: %s", tp)
            return 1
        topic_text = tp.read_text(encoding="utf-8").strip()
        log.info("Loaded topic from file: %s (%s chars)", tp, len(topic_text))

    if topic_text:
        job = parse_topic_line(topic_text)
        if not job:
            log.error("Could not parse topic: %s", topic_text[:120])
            return 1
        jobs = [job]
        log.info("Inline topic mode: %s", job.topic[:100])
    else:
        topics_path = Path(args.topics)
        jobs = load_topics(topics_path)
        if args.limit and args.limit > 0:
            jobs = jobs[: args.limit]
            log.info("Limit active: processing %s topic(s)", len(jobs))
        if not jobs:
            log.error("No topics found in %s", topics_path)
            return 1

    if args.mode == "raw":
        for j in jobs:
            j.director_mode = "raw"

    if not args.dry_run:
        needs_llm = any(_job_needs_ollama(j) for j in jobs)
        if needs_llm and not ollama_reachable():
            log.error("Ollama not reachable at localhost:11434. Start it, then retry.")
            return 1
        if not needs_llm and not ollama_reachable():
            log.info(
                "Ollama offline — OK for locked love/horror/raw screenplays "
                "(keeps GPU free for Flux/Wan)"
            )
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

    log.info("Loaded %s topic(s). dry_run=%s mode=%s", len(jobs), args.dry_run, args.mode)
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
