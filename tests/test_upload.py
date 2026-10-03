from vcut.commons import CommonsFile
from vcut.models import Clip
from vcut.upload import (
    MAX_UPLOAD_BYTES,
    UploadError,
    commons_url,
    upload_file,
    validate_for_upload,
)


def make(tmp_path, name="clip.webm", wikitext="{{Information}}", size=10):
    path = tmp_path / name
    path.write_bytes(b"x" * size)
    return CommonsFile(
        clip=Clip(programme="Talk"), local_path=str(path),
        filename=name, wikitext=wikitext,
    )


def test_a_valid_webm_has_no_problems(tmp_path):
    assert validate_for_upload(make(tmp_path)) == []


def test_mp4_is_rejected(tmp_path):
    problems = validate_for_upload(make(tmp_path, "clip.mp4"))
    assert any("does not accept .mp4" in p for p in problems)


def test_ogv_is_accepted(tmp_path):
    assert validate_for_upload(make(tmp_path, "clip.ogv")) == []


def test_a_missing_file_is_reported(tmp_path):
    prepared = make(tmp_path)
    prepared.local_path = str(tmp_path / "gone.webm")
    assert any("not found" in p for p in validate_for_upload(prepared))


def test_an_empty_file_is_reported(tmp_path):
    assert any("empty" in p for p in validate_for_upload(make(tmp_path, size=0)))


def test_a_file_without_a_description_is_rejected(tmp_path):
    prepared = make(tmp_path, wikitext="   ")
    assert any("description" in p for p in validate_for_upload(prepared))


def test_a_do_not_record_session_is_blocked(tmp_path):
    prepared = make(tmp_path)
    prepared.warnings = ["this session is marked DO NOT RECORD — do not upload it"]
    assert any("do-not-record" in p for p in validate_for_upload(prepared))


def test_an_oversized_file_is_reported(tmp_path, monkeypatch):
    prepared = make(tmp_path)

    class FakeStat:
        st_size = MAX_UPLOAD_BYTES + 1

    monkeypatch.setattr("pathlib.Path.stat", lambda self: FakeStat())
    assert any("4 GiB" in p for p in validate_for_upload(prepared))


def test_a_dry_run_reports_without_uploading(tmp_path):
    assert "would upload" in upload_file(make(tmp_path), dry_run=True)


def test_uploading_an_invalid_file_raises(tmp_path):
    try:
        upload_file(make(tmp_path, "clip.mp4"), dry_run=True)
    except UploadError as exc:
        assert "does not accept" in str(exc)
    else:
        raise AssertionError("expected an UploadError")


def test_commons_url_escapes_the_filename():
    url = commons_url("A Talk (XY12).webm")
    assert url.startswith("https://commons.wikimedia.org/wiki/File:")
    assert " " not in url
