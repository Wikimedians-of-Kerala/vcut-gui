import pytest

from vcut.models import Clip, TimecodeError, format_timecode, parse_timecode


@pytest.mark.parametrize(
    "text,expected",
    [
        ("00:10:59", 659.0),
        ("01:00:48", 3648.0),
        ("02:32:23", 9143.0),
        ("1:30", 90.0),
        ("90", 90.0),
        ("00:00:05.250", 5.25),
        ("  00:01:00  ", 60.0),
        ("00:00:05,5", 5.5),
    ],
)
def test_parse_timecode(text, expected):
    assert parse_timecode(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "abc", "00:99:00", "1:2:3:4", None])
def test_parse_timecode_rejects_junk(text):
    with pytest.raises(TimecodeError):
        parse_timecode(text)


def test_format_timecode_roundtrip():
    assert format_timecode(9143) == "02:32:23"
    assert format_timecode(5.25, with_millis=True) == "00:00:05.250"
    assert parse_timecode(format_timecode(3661)) == 3661


def test_clip_duration():
    clip = Clip(programme="Talk", start_time="00:10:59", end_time="00:33:34")
    assert clip.duration == pytest.approx(1355.0)
    assert clip.is_valid


def test_clip_validation_flags_reversed_times():
    clip = Clip(programme="Talk", start_time="00:05:00", end_time="00:01:00")
    assert "end time must be after start time" in clip.validate()


def test_clip_validation_flags_empty_title():
    clip = Clip(programme="", start_time="00:00:01", end_time="00:00:02")
    assert any("programme" in problem for problem in clip.validate())


def test_clip_validation_against_source_duration():
    clip = Clip(programme="Talk", start_time="00:10:00", end_time="01:00:00")
    assert clip.validate(source_duration=7200) == []
    assert any("exceeds" in p for p in clip.validate(source_duration=1800))
    assert any("past the end" in p for p in clip.validate(source_duration=300))


def test_clip_validation_reports_unparseable_times():
    problems = Clip(programme="Talk", start_time="nope", end_time="00:01:00").validate()
    assert any("start time" in p for p in problems)
