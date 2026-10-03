"""Headless interface, for batch jobs and servers without a display."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .commons import prepare_file, write_sidecar
from .csvio import read_clips
from .eventyay import ScheduleClient, ScheduleError
from .ffmpeg import (
    CutMode,
    EncodingSettings,
    FFmpegError,
    OutputFormat,
    build_command,
    probe,
    run_command,
)
from .manifest import build_entry, write_manifest
from .models import ClipStatus
from .naming import output_path, unique_path
from .settings import AppSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vcut",
        description=(
            "Cut a conference recording into per-session clips and prepare them "
            "for Wikimedia Commons."
        ),
    )
    parser.add_argument("source", help="the full-length recording")
    parser.add_argument("csv", help="the timecode list (CSV or TSV)")
    parser.add_argument(
        "-o", "--output", default="clips", help="where to write the clips"
    )
    parser.add_argument(
        "-f", "--format", default="mp4",
        choices=[fmt.value for fmt in OutputFormat],
        help="output format (default: mp4, which Commons does not accept)",
    )
    parser.add_argument(
        "-m", "--cut-mode", default="smart",
        choices=[mode.value for mode in CutMode],
        help="how to cut (default: smart — accurate and fast)",
    )
    parser.add_argument("-e", "--event", default="",
                        help="event slug or schedule URL for metadata")
    parser.add_argument("--crf", type=int, default=None, help="quality (lower is better)")
    parser.add_argument("--preset", type=int, default=None,
                        help="encoder speed (AV1 preset or VP9 cpu-used)")
    parser.add_argument("--pad-start", type=float, default=0.0,
                        help="seconds of lead-in on every clip")
    parser.add_argument("--pad-end", type=float, default=0.0,
                        help="seconds of lead-out on every clip")
    parser.add_argument("--name-template", default="{index:02d}-{programme}",
                        help="filename template")
    parser.add_argument("--categories", default="",
                        help="semicolon-separated Commons categories")
    parser.add_argument("--license", default="{{Cc-by-sa-4.0}}", dest="license_tag")
    parser.add_argument("--no-subfolders", action="store_true",
                        help="do not separate MP4 cuts from Commons-ready files")
    parser.add_argument("--no-manifest", action="store_true",
                        help="do not write the manifest and descriptions")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--offline", action="store_true",
                        help="use only the cached schedule")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="print the commands without encoding")
    parser.add_argument("-q", "--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    def say(*parts) -> None:
        if not args.quiet:
            print(*parts, flush=True)

    source = Path(args.source)
    if not source.is_file():
        print(f"vcut: '{source}' does not exist", file=sys.stderr)
        return 2

    try:
        clips = read_clips(args.csv)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        print(f"vcut: {exc}", file=sys.stderr)
        return 2
    if not clips:
        print("vcut: the timecode list is empty", file=sys.stderr)
        return 2

    try:
        info = probe(source)
    except FFmpegError as exc:
        print(f"vcut: {exc}", file=sys.stderr)
        return 2
    say(f"Source: {source.name} — {info.duration / 60:.1f} minutes, {info.resolution}")

    fmt = OutputFormat(args.format)
    settings = EncodingSettings().with_format(fmt)
    settings.cut_mode = CutMode(args.cut_mode)
    settings.overwrite = args.overwrite
    settings.pad_start = args.pad_start
    settings.pad_end = args.pad_end
    if args.crf is not None:
        settings.crf = args.crf
    if args.preset is not None:
        if settings.video_codec == "libsvtav1":
            settings.av1_preset = args.preset
        else:
            settings.vp9_cpu_used = args.preset

    if not fmt.commons_compatible:
        say("Note: Commons does not accept MP4. Convert before uploading.")

    schedule: ScheduleClient | None = None
    if args.event:
        try:
            schedule = ScheduleClient(args.event, offline=args.offline)
            sessions = schedule.load()
            say(f"Schedule: {schedule.info.get('title', args.event)} "
                f"({len(sessions)} talks)")
        except ScheduleError as exc:
            say(f"Warning: {exc}")
            schedule = None

    app_settings = AppSettings()
    app_settings.commons_license = args.license_tag
    app_settings.commons_categories = [
        part.strip() for part in args.categories.split(";") if part.strip()
    ]
    commons_settings = app_settings.commons_settings()
    event_info = schedule.info if schedule else {}

    # -- cut ---------------------------------------------------------------

    failures = 0
    produced = 0
    for index, clip in enumerate(clips, start=1):
        problems = clip.validate(info.duration)
        if problems:
            say(f"[{index}/{len(clips)}] skipped {clip.programme!r}: "
                f"{'; '.join(problems)}")
            clip.status = ClipStatus.SKIPPED
            failures += 1
            continue

        target = output_path(
            clip, index, args.output, fmt=fmt,
            filename_template=args.name_template,
            separate_by_format=not args.no_subfolders,
            event=args.event,
        )
        if not args.overwrite:
            target = unique_path(target)
        clip.output_path = str(target)

        try:
            command = build_command(
                source, target, clip.start_seconds, clip.end_seconds, settings
            )
        except (FFmpegError, ValueError) as exc:
            say(f"[{index}/{len(clips)}] {clip.programme}: {exc}")
            failures += 1
            continue

        say(f"[{index}/{len(clips)}] {target.name}")
        if args.dry_run:
            say("    " + " ".join(command))
            clip.status = ClipStatus.DONE
            produced += 1
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        code = run_command(command, clip.duration)
        if code == 0:
            clip.status = ClipStatus.DONE
            produced += 1
        else:
            clip.status = ClipStatus.FAILED
            clip.message = f"ffmpeg exited with code {code}"
            say(f"    failed: {clip.message}")
            failures += 1

    # -- descriptions and manifest ----------------------------------------

    if not args.no_manifest and not args.dry_run:
        entries = []
        for clip in clips:
            if clip.status is not ClipStatus.DONE:
                continue
            session = schedule.get(clip.eventyay_id) if schedule else None
            prepared = prepare_file(
                clip, session=session, settings=commons_settings,
                event_info=event_info, local_path=clip.output_path,
            )
            try:
                write_sidecar(clip.output_path, prepared.wikitext)
            except OSError as exc:
                say(f"Warning: could not write a description: {exc}")
            entries.append(
                build_entry(clip, prepared, session=session, base_directory=args.output)
            )

        if entries:
            try:
                written = write_manifest(
                    args.output, entries, event_info=event_info,
                    source_video=str(source),
                )
                say(f"Wrote {written['json'].name} and {len(entries)} descriptions.")
            except OSError as exc:
                say(f"Warning: could not write the manifest: {exc}")

    say(f"Done: {produced} clips written, {failures} skipped or failed.")
    return 1 if failures and not produced else 0


if __name__ == "__main__":
    raise SystemExit(main())
