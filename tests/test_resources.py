"""Deciding how much encoding this machine can do at once."""

import pytest

from vcut.resources import (
    HEADROOM_MB,
    Machine,
    memory_for,
    plan,
)


def machine(total=16384.0, available=12000.0, cores=8, disk=100000.0) -> Machine:
    return Machine(total, available, cores, disk)


# -- what an encode costs --------------------------------------------------


def test_av1_is_the_expensive_one():
    # Measured: SVT-AV1 at 720p peaked at 952 MB, VP9 at 294 MB.
    assert memory_for("libsvtav1", 1280, 720) > memory_for("libvpx-vp9", 1280, 720)


def test_the_estimate_covers_what_was_measured():
    # Underestimating is the dangerous direction: the kernel kills the job
    # and the user sees "exited with code -11".
    assert memory_for("libsvtav1", 640, 360) >= 376
    assert memory_for("libsvtav1", 1280, 720) >= 952
    assert memory_for("libsvtav1", 1920, 1080) >= 1219


def test_a_bigger_frame_costs_more():
    assert memory_for("libsvtav1", 1920, 1080) > memory_for("libsvtav1", 1280, 720)


def test_an_unknown_codec_is_assumed_expensive():
    assert memory_for("some-new-encoder", 1280, 720) >= memory_for(
        "libvpx-vp9", 1280, 720
    )


# -- the plan --------------------------------------------------------------


def test_a_roomy_machine_may_run_several():
    budget = plan("libvpx-vp9", width=1280, height=720, wanted=4,
                  machine=machine(65536, 60000, 32))
    assert budget.jobs > 1
    assert budget


def test_a_small_machine_runs_one():
    budget = plan("libsvtav1", width=1280, height=720, wanted=4,
                  machine=machine(8192, 4096, 4))
    assert budget.jobs == 1


def test_a_machine_without_room_is_refused_with_advice():
    budget = plan("libsvtav1", width=1920, height=1080, wanted=1,
                  machine=machine(2048, 1700, 4))
    assert not budget
    assert budget.blocked
    # The message must say what to do, not merely that it failed.
    assert "close" in budget.blocked.lower() or "vp9" in budget.blocked.lower()


def test_a_full_disk_is_refused():
    budget = plan("libsvtav1", wanted=1, machine=machine(disk=100.0))
    assert not budget
    assert "disk" in budget.blocked.lower()


def test_never_more_than_asked_for():
    budget = plan("libx264", width=640, height=360, wanted=2,
                  machine=machine(65536, 60000, 64))
    assert budget.jobs <= 2


def test_headroom_is_left_for_the_rest_of_the_system():
    # Encoding must not make the desktop unusable.
    m = machine(8192, HEADROOM_MB + 100.0, 16)
    assert m.usable_memory_mb == pytest.approx(100.0)


def test_the_reason_explains_a_reduced_number():
    budget = plan("libsvtav1", width=1920, height=1080, wanted=8,
                  machine=machine(8192, 6000, 8))
    assert budget.jobs < 8
    assert budget.reason
