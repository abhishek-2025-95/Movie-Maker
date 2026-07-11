from director import parse_topic_line


def test_parse_plain_topic():
    job = parse_topic_line("Secrets of the deep ocean")
    assert job is not None
    assert job.topic == "Secrets of the deep ocean"
    assert job.mode == "faceless"
    assert job.ratio == "9:16"
    assert job.lang == "en"


def test_parse_metadata_pipe():
    job = parse_topic_line(
        "mode:character ratio:16:9 lang:hi | एक जासूस की कहानी"
    )
    assert job is not None
    assert job.mode == "character"
    assert job.ratio == "16:9"
    assert job.lang == "hi"
    assert "जासूस" in job.topic


def test_parse_skips_comments():
    assert parse_topic_line("# comment") is None
    assert parse_topic_line("   ") is None


def test_parse_invalid_meta_falls_back():
    job = parse_topic_line("mode:nope ratio:1:1 lang:fr | Hello world")
    assert job is not None
    assert job.mode == "faceless"
    assert job.ratio == "9:16"
    assert job.lang == "en"
    assert job.topic == "Hello world"
