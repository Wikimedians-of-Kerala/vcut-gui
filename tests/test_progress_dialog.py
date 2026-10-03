"""Confirmation and progress windows."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from vcut.gui.progress_dialog import ConfirmJobDialog, JobProgressDialog, JobSummary  # noqa: E402
from vcut.gui.theme import Theme, apply_theme  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    apply_theme(Theme.DARK)
    yield app


SUMMARY = JobSummary(
    title="Split the video",
    action="Split the video",
    intro="About to cut 3 clips.",
    rows=[("Clips to cut", "3"), ("Total video", "00:00:55")],
    warning="2 clips have not been checked.",
    estimate_seconds=90,
)


def test_the_confirmation_names_its_action(qt_app):
    dialog = ConfirmJobDialog(SUMMARY)
    assert dialog.go.text() == "Split the video"
    assert dialog.windowTitle() == "Split the video"


def test_the_confirmation_is_not_accepted_on_its_own(qt_app):
    # Nothing should start until the user actually presses the button.
    dialog = ConfirmJobDialog(SUMMARY)
    assert dialog.result() != ConfirmJobDialog.Accepted


def test_a_job_with_no_warning_still_builds(qt_app):
    plain = JobSummary(title="T", action="Go", intro="i", rows=[])
    assert ConfirmJobDialog(plain).go.text() == "Go"


def test_progress_starts_empty(qt_app):
    dialog = JobProgressDialog("Splitting", ["a.mp4", "b.mp4"])
    assert dialog.overall.maximum() == 2
    assert dialog.overall.value() == 0
    assert dialog.close_button.isEnabled() is False


def test_progress_tracks_each_job(qt_app):
    dialog = JobProgressDialog("Splitting", ["a.mp4", "b.mp4"])
    dialog.track(7, 0)
    dialog.track(9, 1)
    dialog.set_progress(7, 0.5)
    assert dialog.current.value() == 50
    assert dialog.table.item(0, 1).text() == "50%"


def test_finishing_a_job_advances_the_overall_bar(qt_app):
    dialog = JobProgressDialog("Splitting", ["a.mp4", "b.mp4"])
    dialog.track(0, 0)
    dialog.set_finished(0, True, "")
    assert dialog.overall.value() == 1
    assert dialog.table.item(0, 1).text() == "done"


def test_a_failure_is_shown_against_its_row(qt_app):
    dialog = JobProgressDialog("Splitting", ["a.mp4"])
    dialog.track(0, 0)
    dialog.set_finished(0, False, "ffmpeg exited with code 1")
    assert "ffmpeg" in dialog.table.item(0, 1).text()


def test_completing_enables_close_and_disables_cancel(qt_app):
    dialog = JobProgressDialog("Splitting", ["a.mp4"])
    dialog.complete("1 finished, 0 failed")
    assert dialog.close_button.isEnabled()
    assert dialog.cancel_button.isEnabled() is False


def test_cancelling_emits_once_and_disables_itself(qt_app):
    dialog = JobProgressDialog("Splitting", ["a.mp4"])
    seen = []
    dialog.cancelled.connect(lambda: seen.append(True))
    dialog.cancel_button.click()
    assert seen == [True]
    assert dialog.cancel_button.isEnabled() is False


def test_escape_cannot_close_a_running_job(qt_app):
    # Closing mid-job would leave the worker with nowhere to report.
    dialog = JobProgressDialog("Splitting", ["a.mp4"])
    dialog.show()
    dialog.reject()
    assert dialog.isVisible()
    dialog.complete("done")
    dialog.close()


def test_escape_closes_once_the_job_is_done(qt_app):
    dialog = JobProgressDialog("Splitting", ["a.mp4"])
    dialog.show()
    dialog.complete("done")
    dialog.reject()
    assert not dialog.isVisible()
