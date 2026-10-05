from pathlib import Path

import pytest

from vcut.csvio import map_headers, parse_clips, read_clips, write_clips

TSV = (
    "programme\tstart_time\tend_time\teventyay_id\tauthor\n"
    "Welcome and Opening Remarks\t00:10:59\t00:33:34\t7NXGTK\tAsha Menon, Ravi Kumar\n"
    "Wikimedians of Kerala\t01:31:41\t01:35:42\t\t\n"
)


def test_parses_tab_separated_schedule():
    clips = parse_clips(TSV)
    assert len(clips) == 2
    assert clips[0].programme == "Welcome and Opening Remarks"
    assert clips[0].eventyay_id == "7NXGTK"
    assert clips[0].author.startswith("Asha")


def test_rows_without_an_event_id_are_still_parsed():
    # Several real sessions (performances, video messages) have no talk code.
    clips = parse_clips(TSV)
    assert clips[1].eventyay_id == ""
    assert clips[1].is_valid


def test_parses_comma_separated_file():
    text = "programme,start_time,end_time\nTalk,00:00:10,00:00:20\n"
    clips = parse_clips(text)
    assert len(clips) == 1 and clips[0].programme == "Talk"


def test_legacy_room_name_column_maps_to_programme():
    assert map_headers(["room_name", "start_time", "end_time"]) == {
        "room_name": "programme",
        "start_time": "start_time",
        "end_time": "end_time",
    }


def test_header_aliases_are_case_and_space_insensitive():
    mapping = map_headers(["Session", "Start Time", "End-Time", "Speakers"])
    assert set(mapping.values()) == {"programme", "start_time", "end_time", "author"}


def test_unknown_columns_are_preserved():
    text = "programme,start_time,end_time,notes\nTalk,0:10,0:20,check audio\n"
    assert parse_clips(text)[0].extra == {"notes": "check audio"}


def test_blank_lines_are_skipped():
    text = "programme,start_time,end_time\nTalk,0:10,0:20\n,,\n"
    assert len(parse_clips(text)) == 1


def test_missing_time_columns_is_an_error():
    with pytest.raises(ValueError, match="start and end time"):
        parse_clips("programme,speaker\nTalk,Someone\n")


def test_empty_input_yields_no_clips():
    assert parse_clips("") == []


def test_write_then_read_roundtrip(tmp_path):
    clips = parse_clips(TSV)
    target = tmp_path / "out.csv"
    write_clips(target, clips)
    reloaded = read_clips(target)
    assert [c.programme for c in reloaded] == [c.programme for c in clips]
    assert [c.start_time for c in reloaded] == [c.start_time for c in clips]


def test_read_handles_utf8_bom(tmp_path):
    target = tmp_path / "bom.csv"
    target.write_text("﻿programme,start_time,end_time\nTalk,0:10,0:20\n", encoding="utf-8")
    assert read_clips(target)[0].programme == "Talk"


# -- the shipped examples --------------------------------------------------

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_the_tab_separated_example_parses():
    clips = read_clips(EXAMPLES / "sample-schedule.tsv")
    assert len(clips) == 16
    assert all(not clip.validate() for clip in clips)


def test_the_example_covers_rows_with_and_without_a_talk_code():
    clips = read_clips(EXAMPLES / "sample-schedule.tsv")
    with_code = [c for c in clips if c.eventyay_id]
    without = [c for c in clips if not c.eventyay_id]
    # Both paths matter, so the example must exercise each.
    assert with_code and without


def test_the_minimal_example_parses():
    clips = read_clips(EXAMPLES / "sample-minimal.csv")
    assert len(clips) == 3
    assert all(not clip.validate() for clip in clips)
