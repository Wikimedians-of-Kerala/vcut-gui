"""Keyboard shortcuts.

The bindings follow what video editors have settled on, so the muscle
memory people already have carries over: **Space** to play or pause, **J K
L** to shuttle, **I** and **O** to mark in and out, **,** and **.** to step
a frame at a time.

Everything lives in one table so the help window cannot drift from what the
application actually does — it is generated from this list rather than
written out separately.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Shortcut:
    """One binding: what it does, which keys, and where it applies."""

    action: str
    keys: tuple[str, ...]
    description: str
    group: str
    #: Name of the method it calls, on the screen named by ``target``.
    slot: str = ""
    target: str = ""

    @property
    def primary(self) -> str:
        return self.keys[0] if self.keys else ""

    def display(self) -> str:
        """The keys as a reader expects to see them."""
        return "  or  ".join(_pretty(key) for key in self.keys)


def _pretty(key: str) -> str:
    """Spell a key sequence the way the platform writes it."""
    import sys

    if sys.platform == "darwin":
        key = (key.replace("Ctrl", "⌘").replace("Alt", "⌥")
                  .replace("Shift", "⇧").replace("Meta", "⌃"))
    return (key.replace("Left", "←").replace("Right", "→")
               .replace("Up", "↑").replace("Down", "↓")
               .replace("Space", "Space"))


PLAYBACK = "Playback"
MARKING = "Marking clips"
CLIPS = "The clip list"
NAVIGATION = "Moving around"
FILE = "Files and projects"

#: Every shortcut the application has.
SHORTCUTS: tuple[Shortcut, ...] = (
    # -- playback ----------------------------------------------------------
    Shortcut("Play or pause", ("Space", "K"), "Start or stop playback",
             PLAYBACK, "_toggle_play", "verify"),
    Shortcut("Play backwards", ("J",),
             "Step back a second; press again to keep going",
             PLAYBACK, "_shuttle_back", "verify"),
    Shortcut("Play forwards", ("L",),
             "Step forward a second; press again to keep going",
             PLAYBACK, "_shuttle_forward", "verify"),
    Shortcut("Back one frame", (",", "Left"), "Nudge back a single frame",
             PLAYBACK, "_frame_back", "verify"),
    Shortcut("Forward one frame", (".", "Right"), "Nudge forward a single frame",
             PLAYBACK, "_frame_forward", "verify"),
    Shortcut("Back ten seconds", ("Shift+Left",), "Jump back ten seconds",
             PLAYBACK, "_jump_back", "verify"),
    Shortcut("Forward ten seconds", ("Shift+Right",), "Jump forward ten seconds",
             PLAYBACK, "_jump_forward", "verify"),
    Shortcut("Go to the clip's start", ("Home",),
             "Move the playhead to the selected clip's start",
             PLAYBACK, "_goto_start", "verify"),
    Shortcut("Go to the clip's end", ("End",),
             "Move the playhead to the selected clip's end",
             PLAYBACK, "_goto_end", "verify"),
    Shortcut("Preview the clip", ("P",), "Play the opening seconds of the clip",
             PLAYBACK, "_preview", "verify"),

    # -- marking -----------------------------------------------------------
    Shortcut("Set the start here", ("I",),
             "Use the playhead as the selected clip's start",
             MARKING, "_mark_in", "verify"),
    Shortcut("Set the end here", ("O",),
             "Use the playhead as the selected clip's end",
             MARKING, "_mark_out", "verify"),
    Shortcut("Mark as checked", ("V",),
             "Mark the clip verified and move to the next",
             MARKING, "_mark_verified", "verify"),

    # -- the clip list -----------------------------------------------------
    Shortcut("Add a clip", ("Ctrl+N",),
             "Add a clip starting at the playhead", CLIPS, "_add_clip", "verify"),
    Shortcut("Duplicate the clip", ("Ctrl+D",), "Copy the selected clip",
             CLIPS, "_duplicate_clip", "verify"),
    Shortcut("Remove the clip", ("Delete",),
             "Delete the selected clip from the list",
             CLIPS, "_remove_clip", "verify"),
    Shortcut("Select every clip", ("Ctrl+A",), "Tick all the clips",
             CLIPS, "_select_all_clips", "verify"),
    Shortcut("Select none", ("Ctrl+Shift+A",), "Untick all the clips",
             CLIPS, "_select_no_clips", "verify"),
    Shortcut("Split the video", ("Ctrl+Return",),
             "Start cutting the selected clips",
             CLIPS, "start_cutting", "verify"),

    # -- moving around -----------------------------------------------------
    Shortcut("Next step", ("Ctrl+Right", "Alt+Right"),
             "Go to the next screen", NAVIGATION, "_next_step", ""),
    Shortcut("Previous step", ("Ctrl+Left", "Alt+Left"),
             "Go back a screen", NAVIGATION, "_previous_step", ""),
    Shortcut("Set up", ("Ctrl+1",), "Jump to the first screen",
             NAVIGATION, "", ""),
    Shortcut("Verify and split", ("Ctrl+2",), "Jump to the second screen",
             NAVIGATION, "", ""),
    Shortcut("Metadata", ("Ctrl+3",), "Jump to the third screen",
             NAVIGATION, "", ""),
    Shortcut("Upload", ("Ctrl+4",), "Jump to the fourth screen",
             NAVIGATION, "", ""),
    Shortcut("Zoom in", ("Ctrl++", "Ctrl+="), "Zoom into the timeline",
             NAVIGATION, "_zoom_in", "verify"),
    Shortcut("Zoom out", ("Ctrl+-",), "Zoom out of the timeline",
             NAVIGATION, "_zoom_out", "verify"),
    Shortcut("Fit the timeline", ("Ctrl+0",), "Show the whole recording",
             NAVIGATION, "_zoom_reset", "verify"),

    # -- files -------------------------------------------------------------
    Shortcut("New project", ("Ctrl+Shift+N",), "Start again", FILE),
    Shortcut("Open a project", ("Ctrl+O",), "Open a saved project", FILE),
    Shortcut("Save the project", ("Ctrl+S",), "Save this job", FILE),
    Shortcut("Save as", ("Ctrl+Shift+S",), "Save under another name", FILE),
    Shortcut("Video information", ("Ctrl+I",),
             "Everything FFmpeg knows about the source", FILE),
    Shortcut("Keyboard shortcuts", ("F1", "Ctrl+?"), "This list", FILE),
    Shortcut("Quit", ("Ctrl+Q",), "Close the application", FILE),
)

#: The order groups appear in the help window.
GROUPS = (PLAYBACK, MARKING, CLIPS, NAVIGATION, FILE)


def by_group() -> dict[str, list[Shortcut]]:
    """The shortcuts, grouped for display."""
    grouped: dict[str, list[Shortcut]] = {name: [] for name in GROUPS}
    for shortcut in SHORTCUTS:
        grouped.setdefault(shortcut.group, []).append(shortcut)
    return {name: items for name, items in grouped.items() if items}


def conflicts() -> list[tuple[str, list[str]]]:
    """Key sequences bound to more than one action.

    Two actions answering the same key is a bug the user would only find by
    pressing it, so this is checked by the tests.
    """
    seen: dict[str, list[str]] = {}
    for shortcut in SHORTCUTS:
        for key in shortcut.keys:
            seen.setdefault(key, []).append(shortcut.action)
    return [(key, actions) for key, actions in seen.items() if len(actions) > 1]
