import pytest

from vcut.ffmpeg import (
    FORMAT_DEFAULTS,
    CutMode,
    EncodingSettings,
    OutputFormat,
    build_command,
    build_convert_command,
)


def args_after_input(command):
    return command[command.index("-i") + 2:]


def test_copy_mode_seeks_before_input_and_copies():
    settings = EncodingSettings(cut_mode=CutMode.COPY)
    command = build_command("in.mp4", "out.mp4", 100.0, 160.0, settings)
    assert command.index("-ss") < command.index("-i")
    assert "-c" in command and "copy" in command
    assert "-t" in command and "60.000" in command


def test_smart_mode_splits_the_seek_around_the_input():
    settings = EncodingSettings(cut_mode=CutMode.SMART)
    command = build_command("in.mp4", "out.mp4", 100.0, 160.0, settings)
    # A coarse seek before -i, then a short accurate seek after it.
    assert command.index("-ss") < command.index("-i")
    assert "-ss" in args_after_input(command)
    assert "libx264" in command


def test_smart_mode_does_not_seek_negatively_near_the_start():
    settings = EncodingSettings(cut_mode=CutMode.SMART)
    command = build_command("in.mp4", "out.mp4", 5.0, 10.0, settings)
    first_seek = float(command[command.index("-ss") + 1])
    assert first_seek >= 0.0


def test_reencode_mode_seeks_only_after_the_input():
    settings = EncodingSettings(cut_mode=CutMode.REENCODE)
    command = build_command("in.mp4", "out.mp4", 100.0, 160.0, settings)
    assert command.index("-ss") > command.index("-i")


def test_end_before_start_is_rejected():
    with pytest.raises(ValueError):
        build_command("in.mp4", "out.mp4", 100.0, 50.0, EncodingSettings())


def test_padding_widens_the_clip():
    settings = EncodingSettings(cut_mode=CutMode.COPY, pad_start=2.0, pad_end=3.0)
    command = build_command("in.mp4", "out.mp4", 100.0, 160.0, settings)
    assert command[command.index("-ss") + 1] == "98.000"
    assert command[command.index("-t") + 1] == "65.000"


def test_padding_cannot_seek_before_zero():
    settings = EncodingSettings(cut_mode=CutMode.COPY, pad_start=30.0)
    command = build_command("in.mp4", "out.mp4", 10.0, 20.0, settings)
    assert command[command.index("-ss") + 1] == "0.000"


# --- output formats -------------------------------------------------------

def test_mp4_is_not_accepted_by_commons():
    assert OutputFormat.MP4.commons_compatible is False
    assert OutputFormat.WEBM_AV1.commons_compatible is True
    assert OutputFormat.WEBM_VP9.commons_compatible is True
    assert OutputFormat.OGV.commons_compatible is True


def test_webm_variants_share_the_webm_extension():
    assert OutputFormat.WEBM_AV1.extension == "webm"
    assert OutputFormat.WEBM_VP9.extension == "webm"


def test_commons_default_is_av1_with_opus():
    defaults = FORMAT_DEFAULTS[OutputFormat.WEBM_AV1]
    assert defaults["video_codec"] == "libsvtav1"
    assert defaults["audio_codec"] == "libopus"


def test_with_format_swaps_codecs():
    settings = EncodingSettings().with_format(OutputFormat.WEBM_AV1)
    assert settings.video_codec == "libsvtav1"
    assert settings.audio_codec == "libopus"
    assert settings.container == "webm"


def test_stream_copy_is_upgraded_for_non_mp4_targets():
    # Copying streams cannot change codecs, so a WebM target must re-encode.
    settings = EncodingSettings(cut_mode=CutMode.COPY).with_format(OutputFormat.WEBM_AV1)
    assert settings.cut_mode is CutMode.SMART


def test_copy_mode_never_emits_copy_for_a_webm_target():
    settings = EncodingSettings().with_format(OutputFormat.WEBM_AV1)
    settings.cut_mode = CutMode.COPY  # force it back
    command = build_command("in.mp4", "out.webm", 10.0, 20.0, settings)
    assert "libsvtav1" in command
    assert "copy" not in command


def test_av1_uses_preset_not_cpu_used():
    settings = EncodingSettings().with_format(OutputFormat.WEBM_AV1)
    settings.av1_preset = 6
    command = build_command("in.mp4", "out.webm", 10.0, 20.0, settings)
    assert command[command.index("-preset") + 1] == "6"
    assert "-cpu-used" not in command


def test_vp9_uses_cpu_used_and_constant_quality():
    settings = EncodingSettings().with_format(OutputFormat.WEBM_VP9)
    command = build_command("in.mp4", "out.webm", 10.0, 20.0, settings)
    assert command[command.index("-b:v") + 1] == "0"
    assert "-row-mt" in command


def test_faststart_only_applies_to_mp4():
    mp4 = build_command("in.mp4", "o.mp4", 1.0, 2.0, EncodingSettings())
    webm = build_command(
        "in.mp4", "o.webm", 1.0, 2.0, EncodingSettings().with_format(OutputFormat.WEBM_AV1)
    )
    assert "+faststart" in mp4
    assert "+faststart" not in webm


def test_overwrite_flag_switches_between_y_and_n():
    assert "-n" in build_command("i.mp4", "o.mp4", 1.0, 2.0, EncodingSettings())
    assert "-y" in build_command(
        "i.mp4", "o.mp4", 1.0, 2.0, EncodingSettings(overwrite=True)
    )


def test_settings_survive_a_dict_roundtrip():
    original = EncodingSettings().with_format(OutputFormat.WEBM_AV1)
    original.av1_preset = 4
    restored = EncodingSettings.from_dict(original.to_dict())
    assert restored.output_format is OutputFormat.WEBM_AV1
    assert restored.av1_preset == 4
    assert restored.cut_mode is original.cut_mode


def test_convert_command_transcodes_a_whole_file():
    settings = EncodingSettings().with_format(OutputFormat.WEBM_AV1)
    command = build_convert_command("clip.mp4", "clip.webm", settings)
    assert "-ss" not in command
    assert "libsvtav1" in command


def test_first_vp9_pass_discards_its_output():
    settings = EncodingSettings().with_format(OutputFormat.WEBM_VP9)
    command = build_convert_command("a.mp4", "a.webm", settings, pass_number=1)
    assert command[command.index("-pass") + 1] == "1"
    assert "null" in command
