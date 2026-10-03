from pathlib import Path

from vcut.ffmpeg import OutputFormat
from vcut.models import Clip
from vcut.naming import COMMONS_SUBFOLDER, MP4_SUBFOLDER, output_path, slugify, unique_path


def test_slugify_replaces_separators_and_illegal_characters():
    assert slugify('Who Leads the Commons? Women/Wikimedia') == "Who-Leads-the-Commons-Women-Wikimedia"


def test_slugify_keeps_unicode_by_default():
    assert "സ്കൂൾവിക്കി" in slugify("സ്കൂൾവിക്കി Wiki")


def test_slugify_can_force_ascii():
    assert slugify("സ്കൂൾവിക്കി Wiki Club", ascii_only=True) == "Wiki-Club"


def test_slugify_avoids_windows_reserved_names():
    assert slugify("CON") == "_CON"
    assert slugify("LPT1") == "_LPT1"


def test_slugify_truncates_on_a_word_boundary():
    result = slugify("one two three four five six seven eight", max_length=20)
    assert len(result) <= 20
    assert not result.endswith("-")


def test_slugify_handles_empty_input():
    assert slugify("") == ""
    assert slugify("///") == "clip"


def test_unconverted_mp4_goes_to_its_own_folder():
    clip = Clip(programme="Talk", start_time="0:10", end_time="0:20")
    path = output_path(clip, 1, "/out", fmt=OutputFormat.MP4)
    assert path.parent.name == MP4_SUBFOLDER


def test_commons_formats_share_one_folder():
    clip = Clip(programme="Talk", start_time="0:10", end_time="0:20")
    for fmt in (OutputFormat.WEBM_AV1, OutputFormat.WEBM_VP9, OutputFormat.OGV):
        assert output_path(clip, 1, "/out", fmt=fmt).parent.name == COMMONS_SUBFOLDER


def test_format_folders_can_be_turned_off():
    clip = Clip(programme="Talk", start_time="0:10", end_time="0:20")
    path = output_path(clip, 1, "/out", fmt=OutputFormat.MP4, separate_by_format=False)
    assert path.parent == Path("/out")


def test_extension_follows_the_format():
    clip = Clip(programme="Talk", start_time="0:10", end_time="0:20")
    assert output_path(clip, 1, "/o", fmt=OutputFormat.WEBM_AV1).suffix == ".webm"
    assert output_path(clip, 1, "/o", fmt=OutputFormat.OGV).suffix == ".ogv"


def test_template_tokens_are_substituted():
    clip = Clip(programme="My Talk", start_time="0:10", end_time="0:20", eventyay_id="ABC123")
    path = output_path(clip, 3, "/o", filename_template="{index:02d}-{eventyay_id}-{programme}")
    assert path.stem == "03-ABC123-My-Talk"


def test_subfolder_template_groups_clips():
    clip = Clip(programme="Talk", start_time="0:10", end_time="0:20", room="Grand Ballroom")
    path = output_path(clip, 1, "/o", fmt=OutputFormat.WEBM_AV1, subfolder_template="{room}")
    assert path.parent.name == "Grand-Ballroom"


def test_metadata_title_overrides_the_csv_programme():
    clip = Clip(programme="csv title", start_time="0:10", end_time="0:20")
    clip.metadata = {"title": "schedule title"}
    assert "schedule-title" in output_path(clip, 1, "/o").stem


def test_a_broken_template_still_produces_a_name():
    clip = Clip(programme="Talk", start_time="0:10", end_time="0:20")
    path = output_path(clip, 2, "/o", filename_template="{nonexistent}")
    assert path.stem


def test_unique_path_avoids_collisions(tmp_path):
    first = tmp_path / "clip.mp4"
    first.write_bytes(b"")
    assert unique_path(first).name == "clip-2.mp4"
