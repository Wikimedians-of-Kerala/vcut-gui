"""Hardware encoder detection."""

from vcut.hwaccel import (
    COMMONS_CODECS,
    Backend,
    Capabilities,
    Encoder,
    load_cached,
    save_cached,
)


def caps(*encoders):
    import time

    # A real timestamp, or the cache's age check discards it.
    return Capabilities(encoders=list(encoders), device="/dev/dri/renderD128",
                        probed_at=time.time())


H264 = Encoder(Backend.VAAPI, "h264", "h264_vaapi", works=True)
AV1 = Encoder(Backend.VAAPI, "av1", "av1_vaapi", works=True)
BROKEN = Encoder(Backend.NVENC, "av1", "av1_nvenc", works=False,
                 detail="Cannot load libcuda.so.1")


def test_only_working_encoders_are_offered():
    assert caps(H264, BROKEN).working() == [H264]


def test_commons_codecs_are_the_ones_that_matter():
    assert set(COMMONS_CODECS) == {"av1", "vp9"}
    assert H264.commons_ready is False
    assert AV1.commons_ready is True


def test_a_gpu_without_av1_is_reported_as_such():
    # The common case: hardware H.264 but nothing Commons accepts.
    summary = caps(H264).summary()
    assert "not the formats Commons accepts" in summary
    assert "stays on the CPU" in summary


def test_a_gpu_with_av1_is_reported_as_covering_commons():
    assert "Commons formats are covered" in caps(H264, AV1).summary()


def test_no_hardware_is_said_plainly():
    assert "No working GPU encoder" in caps(BROKEN).summary()


def test_best_for_picks_a_working_encoder():
    assert caps(H264, BROKEN).best_for("h264") is H264
    assert caps(H264, BROKEN).best_for("av1") is None


def test_capabilities_survive_the_cache(tmp_path, monkeypatch):
    import vcut.hwaccel as module

    monkeypatch.setattr(module, "_cache_file", lambda: tmp_path / "hw.json")
    save_cached(caps(H264, BROKEN))
    loaded = load_cached()
    assert loaded is not None
    assert [e.name for e in loaded.encoders] == ["h264_vaapi", "av1_nvenc"]
    assert loaded.working()[0].name == "h264_vaapi"


def test_a_stale_cache_is_ignored(tmp_path, monkeypatch):
    import vcut.hwaccel as module

    monkeypatch.setattr(module, "_cache_file", lambda: tmp_path / "hw.json")
    save_cached(caps(H264))
    assert load_cached(max_age=0) is None


def test_a_corrupt_cache_is_ignored(tmp_path, monkeypatch):
    import vcut.hwaccel as module

    path = tmp_path / "hw.json"
    monkeypatch.setattr(module, "_cache_file", lambda: path)
    path.write_text("not json", encoding="utf-8")
    assert load_cached() is None
