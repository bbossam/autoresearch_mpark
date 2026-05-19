from __future__ import annotations

from autoresearch.agents import ResourceAgent, ResourceRequest
from autoresearch.agents.resource import GpuInfo, MachineState


def _state(machine_id, free_list, disk=100.0, reachable=True):
    gpus = [
        GpuInfo(index=i, mem_total_mb=24000, mem_free_mb=free, util_pct=0)
        for i, free in enumerate(free_list)
    ]
    return MachineState(
        machine_id=machine_id, reachable=reachable, gpus=gpus, disk_free_gb=disk
    )


def test_assess_ready_machine():
    outcome = ResourceAgent().assess(
        _state("m1", [20000, 20000]),
        ResourceRequest(gpus_needed=1, min_free_gpu_mb=10000),
    )

    assert outcome.ok
    assert outcome.data["free_gpus"]


def test_assess_rejects_insufficient_gpu():
    outcome = ResourceAgent().assess(
        _state("m1", [500]),
        ResourceRequest(gpus_needed=1, min_free_gpu_mb=10000),
    )

    assert not outcome.ok


def test_assess_rejects_low_disk():
    outcome = ResourceAgent().assess(
        _state("m1", [20000], disk=5.0),
        ResourceRequest(gpus_needed=1, min_disk_gb=50.0),
    )

    assert not outcome.ok


def test_assess_unreachable_machine():
    outcome = ResourceAgent().assess(
        _state("m1", [], reachable=False), ResourceRequest()
    )

    assert not outcome.ok


def test_place_picks_the_most_capable_machine():
    states = [_state("small", [1000]), _state("big", [22000, 22000])]
    outcome = ResourceAgent().place(
        states, ResourceRequest(gpus_needed=1, min_free_gpu_mb=10000)
    )

    assert outcome.ok
    assert outcome.data["placement"]["machine_id"] == "big"


def test_place_fails_when_no_machine_fits():
    outcome = ResourceAgent().place(
        [_state("small", [1000])], ResourceRequest(min_free_gpu_mb=10000)
    )

    assert not outcome.ok
    assert outcome.data["placement"] is None
