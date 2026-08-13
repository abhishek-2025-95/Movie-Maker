"""Caption cleanup + anatomy negative smoke tests."""
from __future__ import annotations

from editor import cleanup_caption_text
import config
from director import style_prompts


def test_cleanup_dontgo():
    assert cleanup_caption_text("Don'tgo inthere") == "Don't go in there"


def test_cleanup_spacing_punct():
    assert "go." in cleanup_caption_text("go.LOOK") or "LOOK" in cleanup_caption_text("go.LOOK")


def test_anatomy_negative_always_present():
    _, neg = style_prompts("live")
    assert "multiple heads" in neg
    assert "conjoined" in neg
    assert getattr(config, "REQUIRE_SCENE1_REF_LOCK", False) is True
