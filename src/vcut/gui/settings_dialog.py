"""Preferences that outlive one event.

The FFmpeg window covers encoding; this covers everything else — how files
are named on disk and on Commons, where they are put, and how the schedule
is fetched. The per-event choices (licence, categories, the date) stay on
the Metadata screen, where they are seen alongside what they affect.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..settings import AppSettings
from .theme import SPACE_EDGE, SPACE_ROW, SPACE_TIGHT
from .widgets import space_form


class SettingsDialog(QDialog):
    """Everything configurable that is not about encoding."""

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(620, 520)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_EDGE, SPACE_ROW, SPACE_EDGE, SPACE_TIGHT)
        layout.setSpacing(SPACE_ROW)

        tabs = QTabWidget()
        tabs.addTab(self._naming_tab(), "Names")
        tabs.addTab(self._schedule_tab(), "Schedule")
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- tabs --------------------------------------------------------------

    def _naming_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(SPACE_ROW, SPACE_ROW, SPACE_ROW, SPACE_ROW)
        outer.setSpacing(SPACE_ROW)

        commons = QGroupBox("On Commons")
        form = QFormLayout(commons)
        space_form(form)
        form.setLabelAlignment(Qt.AlignRight)

        self.commons_template = QLineEdit(self._settings.commons_filename_template)
        self.commons_template.setPlaceholderText("{title} - {event} ({code}).{ext}")
        self.commons_template.setToolTip(
            "Tokens: {title} {event} {code} {author} {date} {room} {ext}"
        )
        form.addRow("Name pattern", self.commons_template)

        self.include_code = QCheckBox("Add the schedule's talk code")
        self.include_code.setChecked(self._settings.commons_include_code)
        self.include_code.setToolTip(
            "The short code from the conference schedule, such as (JGCFCR).\n"
            "It makes every name unique, which matters when two sessions\n"
            "share a title, but means nothing to most readers."
        )
        form.addRow("", self.include_code)

        self.separator = QComboBox()
        for label, value in (
            ("Space", " "), ("Underscore _", "_"), ("Hyphen -", "-"),
        ):
            self.separator.addItem(label, value)
        index = self.separator.findData(self._settings.commons_word_separator)
        self.separator.setCurrentIndex(index if index >= 0 else 0)
        form.addRow("Between words", self.separator)

        note = QLabel(
            "Commons stores titles with spaces and shows underscores only in "
            "addresses — they mean the same thing there — so this changes how "
            "a name looks rather than how Commons files it."
        )
        note.setWordWrap(True)
        note.setObjectName("screenSubheading")
        form.addRow("", note)
        outer.addWidget(commons)

        disk = QGroupBox("On disk")
        disk_form = QFormLayout(disk)
        space_form(disk_form)
        disk_form.setLabelAlignment(Qt.AlignRight)

        self.disk_template = QLineEdit(self._settings.filename_template)
        self.disk_template.setPlaceholderText("{index:02d}-{programme}")
        self.disk_template.setToolTip(
            "Tokens: {index} {programme} {code} {author} {room} {date}"
        )
        disk_form.addRow("Name pattern", self.disk_template)

        self.subfolder = QLineEdit(self._settings.subfolder_template)
        self.subfolder.setPlaceholderText("leave empty for one flat folder")
        self.subfolder.setToolTip("For example {room}, to group clips by room.")
        disk_form.addRow("Subfolders", self.subfolder)

        self.max_length = QSpinBox()
        self.max_length.setRange(20, 200)
        self.max_length.setValue(self._settings.slug_max_length)
        self.max_length.setSuffix(" characters")
        disk_form.addRow("Longest name", self.max_length)

        self.ascii_only = QCheckBox("Use plain ASCII only")
        self.ascii_only.setChecked(self._settings.ascii_filenames)
        self.ascii_only.setToolTip(
            "Transliterates accents and other scripts, for filesystems or\n"
            "tools that cannot cope with them. Commons names are unaffected."
        )
        disk_form.addRow("", self.ascii_only)

        self.separate_formats = QCheckBox(
            "Keep MP4 cuts and Commons-ready files apart"
        )
        self.separate_formats.setChecked(self._settings.separate_by_format)
        self.separate_formats.setToolTip(
            "So the upload step can point at one folder and trust that\n"
            "everything in it can be uploaded."
        )
        disk_form.addRow("", self.separate_formats)
        outer.addWidget(disk)
        outer.addStretch(1)
        return page

    def _schedule_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(SPACE_ROW, SPACE_ROW, SPACE_ROW, SPACE_ROW)
        outer.setSpacing(SPACE_ROW)

        group = QGroupBox("Conference schedule")
        form = QFormLayout(group)
        space_form(form)
        form.setLabelAlignment(Qt.AlignRight)

        self.auto_fetch = QCheckBox("Look up session details automatically")
        self.auto_fetch.setChecked(self._settings.auto_fetch_metadata)
        form.addRow("", self.auto_fetch)

        self.cache_hours = QSpinBox()
        self.cache_hours.setRange(0, 24 * 30)
        self.cache_hours.setValue(self._settings.cache_ttl_hours)
        self.cache_hours.setSuffix(" hours")
        self.cache_hours.setToolTip(
            "How long a fetched schedule is reused before asking the server\n"
            "again. The whole schedule is fetched once, not once per clip."
        )
        form.addRow("Keep the schedule for", self.cache_hours)

        self.offline = QCheckBox("Work offline")
        self.offline.setChecked(self._settings.offline)
        self.offline.setToolTip(
            "Never touch the network. A schedule already fetched is still\n"
            "used; without one, session details stay as the CSV has them."
        )
        form.addRow("", self.offline)
        outer.addWidget(group)

        files = QGroupBox("Alongside the videos")
        files_form = QFormLayout(files)
        space_form(files_form)
        files_form.setLabelAlignment(Qt.AlignRight)

        self.sidecars = QCheckBox("Write a description file beside each video")
        self.sidecars.setChecked(self._settings.write_sidecars)
        self.sidecars.setToolTip(
            "A .txt of the Commons wikitext, so the folder is enough to\n"
            "finish an upload by hand later."
        )
        files_form.addRow("", self.sidecars)
        outer.addWidget(files)
        outer.addStretch(1)
        return page

    # -- result ------------------------------------------------------------

    def _accept(self) -> None:
        settings = self._settings

        settings.commons_filename_template = (
            self.commons_template.text().strip()
            or "{title} - {event} ({code}).{ext}"
        )
        settings.commons_include_code = self.include_code.isChecked()
        separator = self.separator.currentData()
        settings.commons_word_separator = separator if separator else " "

        settings.filename_template = (
            self.disk_template.text().strip() or "{index:02d}-{programme}"
        )
        settings.subfolder_template = self.subfolder.text().strip()
        settings.slug_max_length = self.max_length.value()
        settings.ascii_filenames = self.ascii_only.isChecked()
        settings.separate_by_format = self.separate_formats.isChecked()

        settings.auto_fetch_metadata = self.auto_fetch.isChecked()
        settings.cache_ttl_hours = self.cache_hours.value()
        settings.offline = self.offline.isChecked()
        settings.write_sidecars = self.sidecars.isChecked()

        settings.save()
        self.accept()
