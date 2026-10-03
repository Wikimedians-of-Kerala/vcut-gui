import json

from vcut.commons import CommonsFile
from vcut.manifest import (
    MANIFEST_CSV,
    MANIFEST_JSON,
    MANIFEST_README,
    build_entry,
    read_manifest,
    write_manifest,
)
from vcut.models import Clip


def make_entry(tmp_path, name="clip.webm", programme="A Talk"):
    clip = Clip(programme=programme, start_time="00:01:00", end_time="00:02:00")
    clip.output_path = str(tmp_path / name)
    (tmp_path / name).write_bytes(b"data")
    prepared = CommonsFile(
        clip=clip, local_path=clip.output_path,
        filename=f"{programme}.webm", wikitext="{{Information}}",
    )
    return build_entry(clip, prepared, base_directory=tmp_path)


def test_entry_marks_webm_as_uploadable(tmp_path):
    assert make_entry(tmp_path, "clip.webm").uploadable is True


def test_entry_marks_mp4_as_not_uploadable(tmp_path):
    assert make_entry(tmp_path, "clip.mp4").uploadable is False


def test_entry_path_is_relative_to_the_output_folder(tmp_path):
    assert make_entry(tmp_path).file == "clip.webm"


def test_entry_points_at_its_description_file(tmp_path):
    assert make_entry(tmp_path).description_file == "clip.txt"


def test_writing_produces_all_three_files(tmp_path):
    write_manifest(tmp_path, [make_entry(tmp_path)])
    for name in (MANIFEST_JSON, MANIFEST_CSV, MANIFEST_README):
        assert (tmp_path / name).is_file()


def test_manifest_json_holds_the_full_wikitext(tmp_path):
    write_manifest(tmp_path, [make_entry(tmp_path)])
    payload = json.loads((tmp_path / MANIFEST_JSON).read_text(encoding="utf-8"))
    assert payload["clips"][0]["wikitext"] == "{{Information}}"
    assert payload["clips"][0]["commons_filename"] == "A Talk.webm"


def test_manifest_records_the_source_and_event(tmp_path):
    write_manifest(
        tmp_path, [make_entry(tmp_path)],
        event_info={"title": "WikiConference India 2026"},
        source_video="/videos/day1.mp4",
    )
    payload = json.loads((tmp_path / MANIFEST_JSON).read_text(encoding="utf-8"))
    assert payload["source_video"] == "/videos/day1.mp4"
    assert payload["event"]["title"] == "WikiConference India 2026"


def test_readme_warns_about_files_that_cannot_be_uploaded(tmp_path):
    write_manifest(tmp_path, [make_entry(tmp_path, "clip.mp4")])
    text = (tmp_path / MANIFEST_README).read_text(encoding="utf-8")
    assert "does not accept MP4" in text
    assert "clip.mp4" in text


def test_readme_lists_uploadable_files_with_their_commons_names(tmp_path):
    write_manifest(tmp_path, [make_entry(tmp_path, "clip.webm", "Opening")])
    text = (tmp_path / MANIFEST_README).read_text(encoding="utf-8")
    assert "Opening.webm" in text
    assert "ready for Wikimedia Commons" in text


def test_manifest_can_be_read_back(tmp_path):
    write_manifest(tmp_path, [make_entry(tmp_path)])
    payload = read_manifest(tmp_path)
    assert payload is not None
    assert len(payload["clips"]) == 1


def test_reading_a_folder_without_a_manifest_returns_none(tmp_path):
    assert read_manifest(tmp_path) is None


def test_csv_lists_one_row_per_clip(tmp_path):
    import csv

    entries = [make_entry(tmp_path, "a.webm", "A"), make_entry(tmp_path, "b.mp4", "B")]
    write_manifest(tmp_path, entries)
    with (tmp_path / MANIFEST_CSV).open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["uploadable"] for row in rows] == ["yes", "no"]
