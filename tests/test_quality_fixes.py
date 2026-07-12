from PIL import Image, ImageDraw

from director import _enrich_visual_prompt
from editor import wrap_caption_by_pixels, _load_font


def test_wrap_never_cuts_mid_word():
    img = Image.new("RGB", (576, 1024))
    draw = ImageDraw.Draw(img)
    font = _load_font(42)
    text = (
        "Strange magnetic anomalies interfere with compass readings and disrupt navigation "
        "for ships crossing the Bermuda Triangle."
    )
    wrapped = wrap_caption_by_pixels(text, draw, font, max_width_px=int(576 * 0.88), max_lines=4)
    assert "naviga" not in wrapped or "navigation" in wrapped.replace("\n", " ")
    for line in wrapped.splitlines():
        # No hyphenated mid-word leftovers from hard char slice
        assert not line.endswith("naviga")
    # All words preserved when they fit across max_lines with shrinking elsewhere
    assert "navigation" in wrapped


def test_enrich_adds_anti_text_and_mood_for_dark_topic():
    out = _enrich_visual_prompt(
        "open ocean under storm clouds",
        "Ships vanish without a trace in the Bermuda Triangle.",
        "Bermuda Triangle mysteries",
    )
    assert "no text" in out.lower()
    assert "mysterious" in out.lower() or "moody" in out.lower()
    assert "cheerful" in out.lower()  # explicitly forbidden aesthetic
