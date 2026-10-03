"""Saving and reopening a job."""

import json

import pytest

from vcut.models import Clip, ClipStatus
from vcut.project import PROJECT_SUFFIX, Project, ProjectError
from vcut.settings import AppSettings


def make_project(tmp_path, *, uploaded=False):
    (tmp_path / "day1.mp4").write_bytes(b"x")
    clip = Clip(
        programme="Opening", start_time="00:10:59", end_time="00:33:34",
        eventyay_id="7NXGTK", author="Someone",
    )
    clip.status = ClipStatus.DONE
    clip.output_path = str(tmp_path / "out" / "01-Opening.mp4")
    clip.converted_path = str(tmp_path / "out" / "01-Opening.webm")
    clip.wikitext = "{{Information}}"
    if uploaded:
        clip.commons_filename = "Opening.webm"
        clip.commons_url = "https://commons.wikimedia.org/wiki/File:Opening.webm"
        clip.uploaded_at = "2026-10-03T12:00:00+00:00"
    return Project(
        source_path=str(tmp_path / "day1.mp4"),
        output_directory=str(tmp_path / "out"),
        event_slug="india26",
        clips=[clip],
        settings=AppSettings(),
        verified={0},
    )


def test_saving_adds_the_suffix(tmp_path):
    written = make_project(tmp_path).save(tmp_path / "day1")
    assert written.suffix == PROJECT_SUFFIX
    assert written.is_file()


def test_a_project_round_trips(tmp_path):
    written = make_project(tmp_path, uploaded=True).save(tmp_path / "day1")
    loaded = Project.load(written)
    assert len(loaded.clips) == 1
    clip = loaded.clips[0]
    assert clip.programme == "Opening"
    assert clip.start_time == "00:10:59"
    assert clip.status is ClipStatus.DONE
    assert clip.wikitext == "{{Information}}"


def test_the_commons_address_survives(tmp_path):
    written = make_project(tmp_path, uploaded=True).save(tmp_path / "day1")
    clip = Project.load(written).clips[0]
    assert clip.commons_url.endswith("File:Opening.webm")
    assert clip.commons_filename == "Opening.webm"
    assert clip.is_uploaded


def test_the_converted_copy_is_remembered_separately(tmp_path):
    # Both are kept: the MP4 for review, the WebM for upload.
    clip = Project.load(make_project(tmp_path).save(tmp_path / "d")).clips[0]
    assert clip.output_path.endswith(".mp4")
    assert clip.converted_path.endswith(".webm")
    assert clip.uploadable_path == clip.converted_path


def test_a_clip_without_a_converted_copy_uploads_its_cut(tmp_path):
    clip = Clip(programme="A", start_time="0:10", end_time="0:20")
    clip.output_path = "/tmp/a.webm"
    assert clip.uploadable_path == "/tmp/a.webm"


def test_checked_marks_survive(tmp_path):
    written = make_project(tmp_path).save(tmp_path / "day1")
    assert Project.load(written).verified == {0}


def test_settings_survive(tmp_path):
    project = make_project(tmp_path)
    project.settings.commons_categories = ["WikiConference India 2026"]
    loaded = Project.load(project.save(tmp_path / "day1"))
    assert loaded.settings.commons_categories == ["WikiConference India 2026"]
    assert loaded.event_slug == "india26"


def test_paths_are_stored_relative_so_the_folder_can_move(tmp_path):
    written = make_project(tmp_path).save(tmp_path / "day1")
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["source_path"] == "day1.mp4"
    assert not payload["clips"][0]["output_path"].startswith("/")


def test_a_moved_project_still_finds_its_files(tmp_path):
    written = make_project(tmp_path).save(tmp_path / "day1")
    moved = tmp_path / "elsewhere"
    moved.mkdir()
    (moved / "day1.vcut").write_text(written.read_text(encoding="utf-8"), encoding="utf-8")
    loaded = Project.load(moved / "day1.vcut")
    # Resolved against the new location, not the old one.
    assert loaded.source_path == str(moved / "day1.mp4")


def test_the_summary_counts_progress(tmp_path):
    assert "1 uploaded" in make_project(tmp_path, uploaded=True).summary()
    assert "0 uploaded" in make_project(tmp_path).summary()


def test_opening_something_that_is_not_a_project_is_an_error(tmp_path):
    bad = tmp_path / "bad.vcut"
    bad.write_text("not json at all", encoding="utf-8")
    with pytest.raises(ProjectError, match="not a valid project"):
        Project.load(bad)


def test_opening_json_that_is_not_a_project_is_an_error(tmp_path):
    bad = tmp_path / "other.vcut"
    bad.write_text('{"something": "else"}', encoding="utf-8")
    with pytest.raises(ProjectError, match="not a vcut project"):
        Project.load(bad)


def test_a_newer_format_is_refused_rather_than_misread(tmp_path):
    newer = tmp_path / "future.vcut"
    newer.write_text(json.dumps({"format": 99, "clips": []}), encoding="utf-8")
    with pytest.raises(ProjectError, match="newer version"):
        Project.load(newer)


def test_a_missing_file_is_an_error(tmp_path):
    with pytest.raises(ProjectError):
        Project.load(tmp_path / "nothing.vcut")


def test_saving_does_not_destroy_the_old_file_on_failure(tmp_path):
    written = make_project(tmp_path).save(tmp_path / "day1")
    original = written.read_text(encoding="utf-8")
    # A save writes through a temporary file and renames it into place.
    make_project(tmp_path, uploaded=True).save(tmp_path / "day1")
    assert written.read_text(encoding="utf-8") != original
    assert not list(tmp_path.glob("*.tmp"))
