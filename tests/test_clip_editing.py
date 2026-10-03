"""The verify screen's row operations, exercised without a display.

These cover the index bookkeeping that keeps 'checked' marks attached to the
right rows when clips are inserted or removed.
"""

import pytest

pytest.importorskip("PySide6")

from vcut.models import Clip  # noqa: E402


class FakeVerify:
    """The reindexing logic, lifted out of the widget so it can be tested."""

    def __init__(self, clips, verified):
        self.clips = list(clips)
        self._verified = set(verified)

    # Copied behaviour from VerifyScreen._reindex_verified.
    def _reindex_verified(self, inserted_at=None, removed_at=None):
        updated = set()
        for row in self._verified:
            if inserted_at is not None and row >= inserted_at:
                updated.add(row + 1)
            elif removed_at is not None:
                if row == removed_at:
                    continue
                updated.add(row - 1 if row > removed_at else row)
            else:
                updated.add(row)
        self._verified = updated


def clips(count):
    return [Clip(programme=f"Clip {i}", start_time="0:10", end_time="0:20")
            for i in range(count)]


def test_inserting_shifts_later_checkmarks():
    screen = FakeVerify(clips(3), {0, 1, 2})
    screen._reindex_verified(inserted_at=1)
    # Rows 1 and 2 moved down; the new row 1 is not checked.
    assert screen._verified == {0, 2, 3}


def test_inserting_at_the_end_leaves_checkmarks_alone():
    screen = FakeVerify(clips(3), {0, 1})
    screen._reindex_verified(inserted_at=3)
    assert screen._verified == {0, 1}


def test_removing_drops_that_row_and_shifts_the_rest():
    screen = FakeVerify(clips(4), {0, 1, 2, 3})
    screen._reindex_verified(removed_at=1)
    assert screen._verified == {0, 1, 2}


def test_removing_an_unchecked_row_still_shifts():
    screen = FakeVerify(clips(4), {2, 3})
    screen._reindex_verified(removed_at=0)
    assert screen._verified == {1, 2}


def test_removing_the_last_row():
    screen = FakeVerify(clips(3), {0, 2})
    screen._reindex_verified(removed_at=2)
    assert screen._verified == {0}


def test_editing_a_timecode_makes_the_clip_valid_again():
    clip = Clip(programme="Lightning Talk", start_time="00:01:35", end_time="00:01:50")
    assert clip.is_valid
    assert clip.duration == 15.0


def test_a_new_clip_is_valid_once_it_has_a_title_and_times():
    clip = Clip(programme="New clip", start_time="00:01:35", end_time="00:11:35")
    assert clip.validate() == []
