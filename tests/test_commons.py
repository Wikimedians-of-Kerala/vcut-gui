from vcut.commons import CommonsSettings, commons_filename, prepare_file, render_description
from vcut.eventyay import Session
from vcut.models import Clip

SESSION = Session(
    code="PQWGTE",
    title="Closing Wikinews",
    abstract="Wikinews was launched with an ambitious promise.",
    description="Closure as stewardship.",
    speakers=["Victoria"],
    day="2026-07-22",
    url="https://wikimedia.eventyay.com/wm/wikimania2026/talk/PQWGTE",
)


def render(clip=None, session=SESSION, settings=None, info=None):
    clip = clip or Clip(programme="Closing Wikinews", eventyay_id="PQWGTE")
    return render_description(clip, session=session, settings=settings, event_info=info)


def test_description_has_the_commons_information_block():
    text, _ = render()
    assert text.startswith("=={{int:filedesc}}==")
    assert "{{Information" in text
    assert "|description={{en|1=" in text


def test_abstract_and_description_are_both_included():
    text, _ = render()
    assert "ambitious promise" in text
    assert "stewardship" in text


def test_source_is_a_bracketed_link_to_the_talk():
    text, _ = render()
    assert f"|source=[{SESSION.url} {SESSION.url}]" in text


def test_author_and_date_come_from_the_schedule():
    text, _ = render()
    assert "|author= Victoria" in text
    assert "|date= 2026-07-22" in text


def test_license_and_categories_are_appended():
    settings = CommonsSettings(license="{{Cc-by-sa-4.0}}", categories=["Cat A", "Cat B"])
    text, _ = render(settings=settings)
    assert "{{Cc-by-sa-4.0}}" in text
    assert "[[Category:Cat A]]" in text
    assert "[[Category:Cat B]]" in text


def test_date_override_wins_over_the_schedule():
    text, _ = render(settings=CommonsSettings(date_override="2026-09-04"))
    assert "|date= 2026-09-04" in text


def test_missing_metadata_is_reported_as_warnings():
    clip = Clip(programme="Untitled", eventyay_id="")
    _, warnings = render_description(clip, session=None)
    joined = " ".join(warnings)
    assert "description" in joined
    assert "author" in joined
    assert "date" in joined


def test_do_not_record_sessions_are_flagged():
    session = Session(code="X", title="Private", do_not_record=True, day="2026-09-04")
    _, warnings = render_description(Clip(programme="Private"), session=session)
    assert any("DO NOT RECORD" in w for w in warnings)


def test_a_broken_custom_template_falls_back():
    settings = CommonsSettings(template="{% for %}")
    text, warnings = render(settings=settings)
    assert "{{Information" in text
    assert any("template error" in w for w in warnings)


def test_commons_filename_is_human_readable():
    name = commons_filename(
        Clip(programme="Closing Wikinews"), session=SESSION,
        event_title="Wikimania 2026", extension="webm",
    )
    assert name == "Closing Wikinews - Wikimania 2026 (PQWGTE).webm"


def test_commons_filename_strips_forbidden_characters():
    session = Session(code="A1", title="Talk: part [1] | #2")
    name = commons_filename(Clip(), session=session, event_title="E", extension="webm")
    assert not any(ch in name[:-5] for ch in '#<>[]|{}:/\\~')


def test_commons_filename_without_a_code_has_no_empty_brackets():
    name = commons_filename(
        Clip(programme="Cultural Performance"), session=None,
        event_title="WikiConference India 2026", extension="webm",
    )
    assert "()" not in name
    assert name.endswith(".webm")


def test_commons_filename_stays_within_the_length_limit():
    session = Session(code="Z9", title="A" * 400)
    name = commons_filename(Clip(), session=session, event_title="E", extension="webm")
    assert len(name.encode("utf-8")) <= 240


def test_preparing_an_mp4_warns_that_commons_rejects_it():
    clip = Clip(programme="Talk", output_path="/tmp/does-not-exist/clip.mp4")
    result = prepare_file(clip, session=SESSION)
    assert any("MP4 cannot be uploaded" in w for w in result.warnings)


def test_preparing_a_webm_does_not_warn_about_the_format():
    clip = Clip(programme="Talk", output_path="/tmp/does-not-exist/clip.webm")
    result = prepare_file(clip, session=SESSION)
    assert not any("MP4" in w for w in result.warnings)


def test_sidecar_is_written_next_to_the_video(tmp_path):
    from vcut.commons import write_sidecar

    video = tmp_path / "clip.webm"
    video.write_bytes(b"")
    written = write_sidecar(video, "hello")
    assert written == tmp_path / "clip.txt"
    assert written.read_text(encoding="utf-8") == "hello"


# -- marking what this tool uploaded ---------------------------------------


def test_every_file_gets_the_tool_category():
    """A maintenance category so the batch can be found and checked later."""
    from vcut.commons import TOOL_CATEGORY, CommonsSettings, render_description
    from vcut.models import Clip

    clip = Clip(programme="A talk", start_time="00:00:00", end_time="00:10:00")
    text, _ = render_description(clip, settings=CommonsSettings())
    assert f"[[Category:{TOOL_CATEGORY}]]" in text


def test_the_tool_category_comes_after_the_subject_ones():
    # The subject categories are what a reader wants first.
    from vcut.commons import TOOL_CATEGORY, CommonsSettings, render_description
    from vcut.models import Clip

    clip = Clip(programme="A talk", start_time="00:00:00", end_time="00:10:00")
    text, _ = render_description(
        clip, settings=CommonsSettings(categories=["Conference videos"])
    )
    assert text.index("Conference videos") < text.index(TOOL_CATEGORY)


def test_the_tool_category_is_not_added_twice():
    from vcut.commons import TOOL_CATEGORY, CommonsSettings, render_description
    from vcut.models import Clip

    clip = Clip(programme="A talk", start_time="00:00:00", end_time="00:10:00")
    text, _ = render_description(
        clip, settings=CommonsSettings(categories=[TOOL_CATEGORY])
    )
    assert text.count(f"[[Category:{TOOL_CATEGORY}]]") == 1


def test_the_tool_category_can_be_turned_off():
    from vcut.commons import TOOL_CATEGORY, CommonsSettings, render_description
    from vcut.models import Clip

    clip = Clip(programme="A talk", start_time="00:00:00", end_time="00:10:00")
    text, _ = render_description(
        clip, settings=CommonsSettings(tag_with_tool=False)
    )
    assert TOOL_CATEGORY not in text


# -- naming a file by hand -------------------------------------------------


def test_a_hand_written_name_wins_over_the_template(tmp_path):
    """The name on Commons is often not the name on disk.

    A talk title the generator truncated, or wording the community has
    agreed on, has to be typeable without renaming the local file.
    """
    from pathlib import Path

    from vcut.commons import CommonsSettings, prepare_file
    from vcut.models import Clip

    video = tmp_path / "09-Schoolwiki.webm"
    video.write_bytes(b"x")

    clip = Clip(programme="Schoolwiki", start_time="00:00:00", end_time="00:10:00")
    clip.output_path = str(video)
    clip.commons_name_override = "A much better name"

    prepared = prepare_file(clip, settings=CommonsSettings())
    assert prepared.filename == "A much better name.webm"
    # The file on disk keeps its own name.
    assert Path(prepared.local_path).name == "09-Schoolwiki.webm"


def test_the_extension_follows_the_real_file(tmp_path):
    # Commons refuses an upload whose name does not match the file, and the
    # extension changes when a clip is converted.
    from vcut.commons import CommonsSettings, prepare_file
    from vcut.models import Clip

    video = tmp_path / "clip.webm"
    video.write_bytes(b"x")
    clip = Clip(programme="A talk", start_time="00:00:00", end_time="00:10:00")
    clip.output_path = str(video)

    clip.commons_name_override = "Named without an extension"
    assert prepare_file(clip, settings=CommonsSettings()).filename.endswith(".webm")

    clip.commons_name_override = "Named with the wrong one.mp4"
    assert prepare_file(clip, settings=CommonsSettings()).filename == (
        "Named with the wrong one.webm"
    )


def test_no_override_means_the_generated_name(tmp_path):
    from vcut.commons import CommonsSettings, prepare_file
    from vcut.models import Clip

    video = tmp_path / "clip.webm"
    video.write_bytes(b"x")
    clip = Clip(programme="A talk", start_time="00:00:00", end_time="00:10:00")
    clip.output_path = str(video)

    assert "A talk" in prepare_file(clip, settings=CommonsSettings()).filename


def test_a_blank_override_is_ignored(tmp_path):
    from vcut.commons import CommonsSettings, prepare_file
    from vcut.models import Clip

    video = tmp_path / "clip.webm"
    video.write_bytes(b"x")
    clip = Clip(programme="A talk", start_time="00:00:00", end_time="00:10:00")
    clip.output_path = str(video)
    clip.commons_name_override = "   "

    assert "A talk" in prepare_file(clip, settings=CommonsSettings()).filename


# -- how the Commons name is built -----------------------------------------


def test_the_talk_code_can_be_left_out():
    """The code makes names unique but means nothing to most readers."""
    from vcut.commons import commons_filename
    from vcut.models import Clip

    clip = Clip(programme="A talk", start_time="0", end_time="1",
                eventyay_id="ABC123")

    with_code = commons_filename(clip, event_title="Conf 2026")
    without = commons_filename(clip, event_title="Conf 2026", include_code=False)

    assert "ABC123" in with_code
    assert "ABC123" not in without
    # And no empty brackets or stray separators left behind.
    assert "()" not in without
    assert " - ." not in without


def test_words_can_be_joined_with_another_character():
    from vcut.commons import commons_filename
    from vcut.models import Clip

    clip = Clip(programme="A longer talk title", start_time="0", end_time="1")

    spaced = commons_filename(clip, word_separator=" ")
    scored = commons_filename(clip, word_separator="_")

    assert " " in spaced
    assert " " not in scored
    assert "A_longer_talk_title" in scored


def test_the_separator_does_not_touch_the_extension():
    from vcut.commons import commons_filename
    from vcut.models import Clip

    clip = Clip(programme="A talk", start_time="0", end_time="1")
    name = commons_filename(clip, word_separator="_", extension="webm")
    assert name.endswith(".webm")
    assert name.count(".") == 1


def test_both_options_together():
    from vcut.commons import commons_filename
    from vcut.models import Clip

    clip = Clip(programme="A talk", start_time="0", end_time="1",
                eventyay_id="ABC123")
    name = commons_filename(
        clip, event_title="Conf 2026", include_code=False, word_separator="_"
    )
    assert "ABC123" not in name and " " not in name


def test_the_settings_reach_the_renderer():
    from vcut.settings import AppSettings

    settings = AppSettings()
    settings.commons_include_code = False
    settings.commons_word_separator = "_"

    commons = settings.commons_settings()
    assert commons.include_code is False
    assert commons.word_separator == "_"
