from director import parse_topic_line, _enrich_visual_prompt
from editor import wrap_caption_by_pixels, _load_font, _fit_caption
from PIL import Image, ImageDraw


def test_wrap_never_cuts_mid_word():
    img = Image.new("RGB", (576, 1024))
    draw = ImageDraw.Draw(img)
    font = _load_font(42)
    text = (
        "Strange magnetic anomalies interfere with compass readings and disrupt navigation "
        "for ships crossing the Bermuda Triangle."
    )
    wrapped = wrap_caption_by_pixels(text, draw, font, max_width_px=int(576 * 0.88), max_lines=4)
    for line in wrapped.splitlines():
        assert not line.endswith("naviga")
        assert " " in line or len(line) < 20 or line.isalpha()
    # Fitted caption keeps full sentence via font shrink
    fitted, _font = _fit_caption(text, draw, max_box_w=int(768 * 0.90))
    assert "navigation" in fitted.replace("\n", " ")
    assert "Triangle" in fitted.replace("\n", " ")


def test_enrich_adds_anti_text_and_mood_for_dark_topic():
    out = _enrich_visual_prompt(
        "open ocean under storm clouds",
        "Ships vanish without a trace in the Bermuda Triangle.",
        "Bermuda Triangle mysteries",
        style="live",
    )
    assert "no text" in out.lower()
    assert "mysterious" in out.lower() or "moody" in out.lower()
    assert "cheerful" in out.lower()  # explicitly forbidden aesthetic


def test_parse_animated_style():
    job = parse_topic_line(
        "mode:character style:animated ratio:9:16 lang:hi | प्यार की कहानी"
    )
    assert job is not None
    assert job.style == "animated"
    assert job.mode == "character"
    assert job.lang == "hi"
