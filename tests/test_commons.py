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
