"""The help window and the text it shows."""

import re

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from vcut.gui.help_content import TOPICS, by_key, for_screen  # noqa: E402

#: The screens the main window can be showing, in order.
SCREENS = ("setup", "verify", "metadata", "upload")


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


# -- the content -----------------------------------------------------------


def test_topic_keys_are_unique():
    keys = [topic.key for topic in TOPICS]
    assert len(keys) == len(set(keys))


def test_every_topic_has_a_title_and_a_body():
    for topic in TOPICS:
        assert topic.title.strip(), topic.key
        assert len(topic.body.strip()) > 200, f"{topic.key} looks like a stub"


def test_every_screen_has_a_topic():
    # A new screen without help is the failure this is here to catch.
    for screen in SCREENS:
        assert for_screen(screen) is not None, f"no help topic for {screen}"


def test_no_topic_claims_an_unknown_screen():
    for topic in TOPICS:
        if topic.screen:
            assert topic.screen in SCREENS, f"{topic.key} -> {topic.screen}"


def test_each_screen_is_claimed_once():
    claimed = [topic.screen for topic in TOPICS if topic.screen]
    assert len(claimed) == len(set(claimed))


def test_bodies_use_only_tags_qlabel_renders():
    # QLabel's rich text is a subset of HTML; anything else renders as
    # literal angle brackets in the window.
    allowed = {"p", "b", "i", "ul", "ol", "li", "br", "tt", "/p", "/b", "/i",
               "/ul", "/ol", "/li", "/tt"}
    for topic in TOPICS:
        for tag in re.findall(r"<\s*(/?\w+)", topic.body):
            assert tag.lower() in allowed, f"{topic.key}: <{tag}>"


def test_bodies_have_balanced_paragraph_tags():
    for topic in TOPICS:
        for tag in ("p", "ul", "ol", "li"):
            opened = len(re.findall(rf"<{tag}>", topic.body))
            closed = len(re.findall(rf"</{tag}>", topic.body))
            assert opened == closed, f"{topic.key}: <{tag}> {opened}/{closed}"


def test_by_key_finds_topics_and_tolerates_misses():
    assert by_key("overview") is not None
    assert by_key("no-such-topic") is None


# -- the window ------------------------------------------------------------


def test_opens_on_the_topic_for_the_screen(qt_app):
    from vcut.gui.help_dialog import HelpDialog

    for screen in SCREENS:
        dialog = HelpDialog(screen=screen)
        assert dialog.heading.text() == for_screen(screen).title


def test_opens_on_the_overview_without_a_screen(qt_app):
    from vcut.gui.help_dialog import HelpDialog

    assert HelpDialog().heading.text() == TOPICS[0].title


def test_unknown_screen_falls_back_rather_than_failing(qt_app):
    from vcut.gui.help_dialog import HelpDialog

    assert HelpDialog(screen="nowhere").heading.text() == TOPICS[0].title


def test_every_topic_is_listed(qt_app):
    from vcut.gui.help_dialog import HelpDialog

    dialog = HelpDialog()
    listed = [dialog.topics.item(i).text() for i in range(dialog.topics.count())]
    assert listed == [topic.title for topic in TOPICS]


def test_choosing_a_topic_shows_it(qt_app):
    from vcut.gui.help_dialog import HelpDialog

    dialog = HelpDialog()
    dialog.topics.setCurrentRow(3)
    assert dialog.heading.text() == TOPICS[3].title
    assert dialog.body.text().strip() == TOPICS[3].body.strip()


def test_search_matches_the_body_not_only_the_title(qt_app):
    from vcut.gui.help_dialog import HelpDialog

    # "keyframe" appears in no title, so a title-only search would miss the
    # topic that actually explains it.
    dialog = HelpDialog()
    dialog.search.setText("keyframe")
    shown = [
        dialog.topics.item(i).text()
        for i in range(dialog.topics.count())
        if not dialog.topics.item(i).isHidden()
    ]
    assert shown
    assert "Why the cuts land where they do" in shown


def test_search_matches_keywords(qt_app):
    from vcut.gui.help_dialog import HelpDialog

    # "2fa" is a keyword on the login topic, not words in its prose.
    dialog = HelpDialog()
    dialog.search.setText("2fa")
    shown = [
        dialog.topics.item(i).text()
        for i in range(dialog.topics.count())
        if not dialog.topics.item(i).isHidden()
    ]
    assert shown == ["Signing in to Commons"]


def test_search_moves_off_a_hidden_selection(qt_app):
    from vcut.gui.help_dialog import HelpDialog

    dialog = HelpDialog()
    dialog.topics.setCurrentRow(0)
    dialog.search.setText("passkey")
    current = dialog.topics.currentItem()
    assert current is not None and not current.isHidden()
    assert dialog.heading.text() == current.text()


def test_clearing_the_search_restores_every_topic(qt_app):
    from vcut.gui.help_dialog import HelpDialog

    dialog = HelpDialog()
    dialog.search.setText("passkey")
    dialog.search.setText("")
    hidden = [
        i for i in range(dialog.topics.count()) if dialog.topics.item(i).isHidden()
    ]
    assert hidden == []
    assert dialog.count.text() == f"{len(TOPICS)} topics"


def test_a_search_matching_nothing_hides_everything(qt_app):
    from vcut.gui.help_dialog import HelpDialog

    dialog = HelpDialog()
    dialog.search.setText("zzzznotathing")
    shown = [
        i for i in range(dialog.topics.count())
        if not dialog.topics.item(i).isHidden()
    ]
    assert shown == []
    assert dialog.count.text() == f"0 of {len(TOPICS)} topics"


def test_help_is_in_the_help_menu_on_f1(qt_app):
    from vcut.gui.main_window import MainWindow

    window = MainWindow()
    menu = next(
        action.menu()
        for action in window.menuBar().actions()
        if "Help" in action.text()
    )
    bindings = {
        action.text(): [key.toString() for key in action.shortcuts()]
        for action in menu.actions()
        if not action.isSeparator()
    }
    help_entry = next(text for text in bindings if "How to use" in text)
    assert "F1" in bindings[help_entry]

    # The shortcut list keeps a binding of its own rather than losing one.
    shortcut_entry = next(text for text in bindings if "Keyboard" in text)
    assert bindings[shortcut_entry]
