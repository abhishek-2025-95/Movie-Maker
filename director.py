"""Topic parsing + Ollama cinematic director."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import requests

import config


@dataclass
class TopicJob:
    topic: str
    mode: str = config.DEFAULT_MODE
    ratio: str = config.DEFAULT_RATIO
    lang: str = config.DEFAULT_LANG


@dataclass
class Scene:
    narration: str
    visual_prompt: str
    motion_prompt: str = "slow cinematic camera push-in, subtle ambient motion"


@dataclass
class Screenplay:
    title: str
    scenes: list[Scene] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


_META_RE = re.compile(
    r"^(?:(?:mode|ratio|lang)\s*:\s*[^\s|]+(?:\s+|\s*\|\s*))*",
    re.IGNORECASE,
)
_KV_RE = re.compile(r"(mode|ratio|lang)\s*:\s*([^\s|]+)", re.IGNORECASE)


def parse_topic_line(line: str) -> TopicJob | None:
    text = line.strip()
    if not text or text.startswith("#"):
        return None

    meta: dict[str, str] = {}
    for match in _KV_RE.finditer(text):
        meta[match.group(1).lower()] = match.group(2).strip().lower()

    topic = _META_RE.sub("", text)
    topic = topic.lstrip("|").strip()
    if not topic:
        # allow "mode:faceless ratio:16:9 lang:en The topic"
        # if regex ate everything wrongly, fall back
        topic = _KV_RE.sub("", text).strip(" |")
    if not topic:
        return None

    mode = meta.get("mode", config.DEFAULT_MODE)
    ratio = meta.get("ratio", config.DEFAULT_RATIO)
    lang = meta.get("lang", config.DEFAULT_LANG)

    if mode not in {"faceless", "character"}:
        mode = config.DEFAULT_MODE
    if ratio not in config.RATIO_SIZES:
        ratio = config.DEFAULT_RATIO
    if lang not in {"en", "hi"}:
        lang = config.DEFAULT_LANG

    return TopicJob(topic=topic, mode=mode, ratio=ratio, lang=lang)


def load_topics(path=None) -> list[TopicJob]:
    path = path or config.TOPICS_FILE
    jobs: list[TopicJob] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        job = parse_topic_line(line)
        if job:
            jobs.append(job)
    return jobs


def _director_system_prompt(job: TopicJob, scene_count: int) -> str:
    lang_name = "Hindi (Devanagari script)" if job.lang == "hi" else "English"
    style = (
        "character-driven narrative with a consistent protagonist appearance"
        if job.mode == "character"
        else "faceless documentary B-roll (no recurring face required)"
    )
    return f"""You are an elite cinematic director and prompt engineer for AI video.
Return ONLY valid JSON (no markdown) with this schema:
{{
  "title": "short title",
  "scenes": [
    {{
      "narration": "spoken VO line in {lang_name}",
      "visual_prompt": "detailed still-image prompt for Flux, subject, lighting, lens, mood",
      "motion_prompt": "short camera/motion instruction for image-to-video"
    }}
  ]
}}
Rules:
- Exactly {scene_count} scenes.
- Style: {style}, aspect mindset {job.ratio}.
- Narration: natural spoken {lang_name}, ~12-22 words per scene, no stage directions.
- visual_prompt: concrete, photographic, no text/logos/watermarks.
- motion_prompt: subtle cinematic motion only (pan/tilt/push/parallax), no cuts.
- Keep character wardrobe/face descriptors identical across scenes when mode is character.
"""


def generate_screenplay(job: TopicJob, scene_count: int | None = None) -> Screenplay:
    n = scene_count or config.SCENES_PER_VIDEO
    system = _director_system_prompt(job, n)
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": f"Topic: {job.topic}\n\n{system}",
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.7},
    }
    resp = requests.post(config.OLLAMA_URL, json=payload, timeout=180)
    resp.raise_for_status()
    body = resp.json()
    raw_text = body.get("response") or "{}"
    data = json.loads(raw_text)
    return _parse_screenplay(data, job.topic)


def _parse_screenplay(data: dict[str, Any], fallback_title: str) -> Screenplay:
    scenes_raw = data.get("scenes") or []
    scenes: list[Scene] = []
    for item in scenes_raw:
        if not isinstance(item, dict):
            continue
        narration = str(item.get("narration") or "").strip()
        visual = str(item.get("visual_prompt") or item.get("visual") or "").strip()
        motion = str(item.get("motion_prompt") or item.get("motion") or "").strip()
        if not narration and not visual:
            continue
        scenes.append(
            Scene(
                narration=narration or "...",
                visual_prompt=visual or "cinematic establishing shot",
                motion_prompt=motion or "slow cinematic push-in",
            )
        )
    title = str(data.get("title") or fallback_title).strip()
    return Screenplay(title=title, scenes=scenes, raw=data)


def ollama_reachable() -> bool:
    try:
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        return r.ok
    except requests.RequestException:
        return False
