"""Local voiceover generation: XTTS (best) with edge-tts fallback."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

import config

log = logging.getLogger(__name__)


def _cache_path(text: str, lang: str, out_dir: Path) -> Path:
    digest = hashlib.sha1(f"{lang}|{text}".encode("utf-8")).hexdigest()[:16]
    return out_dir / f"vo_{digest}.wav"


def synthesize(
    text: str,
    *,
    lang: str = "en",
    out_path: Path | None = None,
    voice_sample: Path | None = None,
) -> Path:
    """Generate narration audio. Prefers XTTS when installed + sample present."""
    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = out_path or _cache_path(text, lang, config.TEMP_DIR)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sample = voice_sample or config.VOICE_SAMPLE
    backend = config.VOICE_BACKEND

    if backend in {"auto", "xtts"} and _xtts_available() and sample.exists():
        try:
            _synthesize_xtts(text, lang=lang, out_path=out_path, speaker_wav=sample)
            return out_path
        except Exception as exc:  # noqa: BLE001
            log.warning("XTTS failed (%s); falling back to edge-tts", exc)
            if backend == "xtts":
                raise

    _synthesize_edge(text, lang=lang, out_path=out_path)
    return out_path


def _xtts_available() -> bool:
    try:
        import TTS  # noqa: F401

        return True
    except ImportError:
        return False


def _synthesize_xtts(text: str, *, lang: str, out_path: Path, speaker_wav: Path) -> None:
    from TTS.api import TTS

    xtts_lang = config.XTTS_LANGUAGE.get(lang, "en")
    # Lazy singleton on function attribute
    if not hasattr(_synthesize_xtts, "_model"):
        _synthesize_xtts._model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        try:
            _synthesize_xtts._model.to("cuda")
        except Exception:  # noqa: BLE001
            pass
    model = _synthesize_xtts._model
    model.tts_to_file(
        text=text,
        file_path=str(out_path),
        speaker_wav=str(speaker_wav),
        language=xtts_lang,
    )


def _synthesize_edge(text: str, *, lang: str, out_path: Path) -> None:
    voice = "hi-IN-MadhurNeural" if lang == "hi" else "en-US-AndrewNeural"
    mp3_path = out_path.with_suffix(".mp3")

    async def _run() -> None:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(mp3_path))

    asyncio.run(_run())

    # Prefer wav for MoviePy consistency; convert via moviepy if needed
    if mp3_path.exists() and out_path.suffix.lower() == ".wav":
        try:
            from moviepy.editor import AudioFileClip

            clip = AudioFileClip(str(mp3_path))
            clip.write_audiofile(str(out_path), verbose=False, logger=None)
            clip.close()
            mp3_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            # Keep mp3 if conversion fails
            if out_path.exists():
                out_path.unlink()
            mp3_path.rename(out_path.with_suffix(".mp3"))
            return
    elif mp3_path.exists() and not out_path.exists():
        mp3_path.rename(out_path)
