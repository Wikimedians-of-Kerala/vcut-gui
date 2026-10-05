"""Generating Wikimedia Commons file descriptions.

Produces the ``{{Information}}`` wikitext that accompanies each uploaded clip,
and the Commons filename to upload it under. Kept free of any upload logic so
the same rendering is used for sidecar files and for pywikibot uploads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, TemplateError

from .eventyay import Session
from .models import Clip

#: The default description template. Mirrors the layout Commons expects:
#: an {{Information}} block, then licensing, then categories.
DEFAULT_TEMPLATE = """\
=={{int:filedesc}}==
{{Information
|description={{{{{{language}}|1= {{description} }}}
|date= {{date}
|source={{source}
|author= {{author}
}}

=={{int:license-header}}==
{{license}
{% for category in categories %}[[Category:{{ category }}]]
{% endfor %}"""

# Jinja and MediaWiki both use braces; build the template with explicit markers
# instead of fighting the escaping.
_TEMPLATE_BODY = """\
=={{ '{{int:filedesc}}' }}==
{{ '{{Information' }}
|description={{ '{{' }}{{ language }}|1= {{ description }} {{ '}}' }}
|date= {{ date }}
|source={{ source }}
|author= {{ author }}
{{ '}}' }}
{% if license %}
=={{ '{{int:license-header}}' }}==
{{ license }}
{% endif %}
{% if categories %}
{% for category in categories %}[[Category:{{ category }}]]
{% endfor %}
{% endif %}"""

DEFAULT_TEMPLATE = _TEMPLATE_BODY

#: Characters Commons does not allow in a file name.
_COMMONS_ILLEGAL = r'#<>[]|{}:/\~'


#: Added to every upload so the batch can be found, checked or undone later.
#: A maintenance category like this is ordinary practice on Commons: it costs
#: the uploader nothing and gives anyone reviewing the files a single place
#: to see what this tool produced.
TOOL_CATEGORY = "Uploaded with vcut"


def _categories(settings: "CommonsSettings") -> list[str]:
    """The categories for one file, with the tool's own added last.

    Last because the subject categories are what a reader wants first; the
    maintenance one is for whoever is checking the batch.
    """
    categories = [c for c in settings.categories if c.strip()]
    if settings.tag_with_tool and TOOL_CATEGORY not in categories:
        categories.append(TOOL_CATEGORY)
    return categories


@dataclass
class CommonsSettings:
    """Options governing the generated description."""

    license: str = "{{Cc-by-sa-4.0}}"
    categories: list[str] = field(default_factory=list)
    #: Whether to add :data:`TOOL_CATEGORY`. On by default; off for anyone
    #: who would rather not categorise by tool.
    tag_with_tool: bool = True
    template: str = ""
    date_override: str = ""
    filename_template: str = "{title} - {event} ({code}).{ext}"
    #: Whether the schedule's talk code goes in the name.
    include_code: bool = True
    #: What separates words in the name. Commons treats spaces and
    #: underscores as the same character, so this is a matter of taste.
    word_separator: str = " "
    language: str = "en"
    append_text: str = ""


@dataclass
class CommonsFile:
    """A clip prepared for Commons: local file, target name, and description."""

    clip: Clip
    local_path: str = ""
    filename: str = ""
    wikitext: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def is_uploadable(self) -> bool:
        return bool(self.local_path) and bool(self.filename) and bool(self.wikitext)


def _with_extension(name: str, extension: str) -> str:
    """Make sure a hand-written name ends in the file's real extension.

    Commons refuses an upload whose name does not match the file, and the
    extension is not something the user should have to remember -- or have
    to change when a clip is converted.
    """
    stem = Path(name).stem if Path(name).suffix else name
    return f"{stem.strip()}.{extension}"


def commons_filename(
    clip: Clip,
    *,
    session: Session | None = None,
    event_title: str = "",
    extension: str = "webm",
    template: str = "{title} - {event} ({code}).{ext}",
    max_length: int = 200,
    include_code: bool = True,
    word_separator: str = " ",
) -> str:
    """Build the name the file will carry on Commons.

    Commons names are human-readable with spaces, unlike local filenames, but
    still forbid a handful of characters and cap the length at 240 bytes.
    """
    title = (session.title if session else "") or clip.programme or "Video"
    code = (session.code if session else "") or clip.eventyay_id or ""
    if not include_code:
        # Left empty rather than removed from the template, so the tidying
        # below strips the brackets and stray separators it leaves behind.
        code = ""

    name = template.format(
        title=title, event=event_title, code=code, ext=extension,
        author=(session.author if session else clip.author),
        date=(session.day if session else ""),
        room=(session.room if session else clip.room),
    )

    # Drop empty bracketed fragments and the separators left stranded beside
    # them when a value such as the event title is missing.
    name = re.sub(r"\(\s*\)", "", name)
    name = re.sub(r"\s*-\s*-\s*", " - ", name)
    name = re.sub(r"\s*-\s*(?=\.|$)", "", name)
    name = re.sub(r"\s*-\s*(?=\()", " ", name)
    name = re.sub(r"(?<=\()\s*-\s*", "", name)
    name = "".join(" " if ch in _COMMONS_ILLEGAL else ch for ch in name if ord(ch) >= 32)
    name = re.sub(r"\s{2,}", " ", name).strip()
    name = re.sub(r"\s+\.", ".", name)

    stem, _, ext = name.rpartition(".")
    if not stem:
        stem, ext = name, extension

    # Commons caps filenames at 240 bytes including the extension.
    budget = min(max_length, 240 - len(ext) - 1)
    encoded = stem.encode("utf-8")
    if len(encoded) > budget:
        stem = encoded[:budget].decode("utf-8", "ignore").rstrip(" -_")

    if word_separator and word_separator != " ":
        stem = stem.replace(" ", word_separator)

    return f"{stem}.{ext}"


def render_description(
    clip: Clip,
    *,
    session: Session | None = None,
    settings: CommonsSettings | None = None,
    event_info: dict | None = None,
) -> tuple[str, list[str]]:
    """Render the Commons wikitext for one clip.

    Returns the text and a list of warnings about anything missing that a
    reviewer on Commons would otherwise flag.
    """
    settings = settings or CommonsSettings()
    event_info = event_info or {}
    warnings: list[str] = []

    description = ""
    if session:
        description = session.full_description
    if not description:
        description = (clip.metadata or {}).get("description", "")
    if not description:
        warnings.append("no description available — add one before uploading")

    author = (session.author if session else "") or clip.author
    if not author:
        warnings.append("no author/speaker recorded")

    date = settings.date_override
    if not date and session:
        date = session.day or (session.date or "")[:10]
    if not date:
        date = event_info.get("start", "")
    if not date:
        warnings.append("no date — Commons requires one")

    source = ""
    if session and session.url:
        source = f"[{session.url} {session.url}]"
    elif event_info.get("url"):
        source = f"[{event_info['url']} {event_info['url']}]"
    else:
        warnings.append("no source URL")

    if session and session.do_not_record:
        warnings.append("this session is marked DO NOT RECORD — do not upload it")

    title = (session.title if session else "") or clip.programme
    language = (session.language if session else settings.language) or "en"

    context = {
        "title": title,
        "description": description.strip(),
        "date": date,
        "source": source,
        "author": author,
        "license": settings.license,
        "categories": _categories(settings),
        "language": language,
        "code": (session.code if session else clip.eventyay_id),
        "event": event_info.get("title", ""),
        "room": (session.room if session else clip.room),
        "track": (session.track if session else ""),
    }

    template_text = settings.template.strip() or DEFAULT_TEMPLATE
    environment = Environment(autoescape=False, keep_trailing_newline=True)
    try:
        rendered = environment.from_string(template_text).render(**context)
    except TemplateError as exc:
        warnings.append(f"template error ({exc}); used the built-in template")
        rendered = environment.from_string(DEFAULT_TEMPLATE).render(**context)

    # Collapse the blank lines Jinja's block tags leave behind.
    rendered = re.sub(r"\n{3,}", "\n\n", rendered).strip() + "\n"

    if settings.append_text.strip():
        rendered += "\n" + settings.append_text.strip() + "\n"

    return rendered, warnings


def prepare_file(
    clip: Clip,
    *,
    session: Session | None = None,
    settings: CommonsSettings | None = None,
    event_info: dict | None = None,
    local_path: str = "",
) -> CommonsFile:
    """Build the complete Commons payload for one clip."""
    settings = settings or CommonsSettings()
    event_info = event_info or {}
    # The converted copy is what gets uploaded, when there is one.
    path = local_path or clip.uploadable_path

    wikitext, warnings = render_description(
        clip, session=session, settings=settings, event_info=event_info
    )

    extension = Path(path).suffix.lstrip(".") or "webm"
    if extension == "mp4":
        warnings.append(
            "MP4 cannot be uploaded to Commons — convert this clip to WebM first"
        )

    # A name chosen by hand wins over the template. The extension still
    # comes from the actual file, since Commons rejects a mismatch.
    override = (clip.commons_name_override or "").strip()
    if override:
        filename = _with_extension(override, extension)
    else:
        filename = commons_filename(
            clip,
            session=session,
            event_title=event_info.get("title", ""),
            extension=extension,
            template=settings.filename_template,
            include_code=settings.include_code,
            word_separator=settings.word_separator,
        )

    if path and not Path(path).is_file():
        warnings.append("the clip file does not exist yet")

    return CommonsFile(
        clip=clip, local_path=path, filename=filename,
        wikitext=wikitext, warnings=warnings,
    )


def sidecar_path(video_path: str | Path) -> Path:
    """Where the ``.txt`` description sits next to its video."""
    return Path(video_path).with_suffix(".txt")


def write_sidecar(video_path: str | Path, wikitext: str) -> Path:
    """Write the description beside the video file."""
    target = sidecar_path(video_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(wikitext, encoding="utf-8")
    return target
