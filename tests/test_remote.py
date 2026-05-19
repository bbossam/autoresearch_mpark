from __future__ import annotations

from autoresearch.models import EnvKind, EnvSpec, MachineCapsule
from autoresearch.remote import (
    build_run_command,
    build_sbatch_script,
    env_prefix,
    parse_nvidia_smi,
)


def test_parse_nvidia_smi():
    gpus = parse_nvidia_smi("0, 24000, 20000, 5\n1, 24000, 100, 95\n")

    assert len(gpus) == 2
    assert gpus[0].mem_free_mb == 20000
    assert gpus[1].util_pct == 95


def test_parse_nvidia_smi_ignores_garbage():
    assert parse_nvidia_smi("no GPU detected\n") == []


def test_env_prefix_docker_and_conda():
    docker = env_prefix(EnvSpec(kind=EnvKind.docker, image="autoresearch:latest"))
    assert "docker" in docker and "autoresearch:latest" in docker

    conda = env_prefix(EnvSpec(kind=EnvKind.conda, conda_env="ar"))
    assert "conda" in conda and "ar" in conda


def test_build_run_command_pins_gpus():
    cmd = build_run_command(
        EnvSpec(kind=EnvKind.conda, conda_env="ar"), "python train.py", [0, 1]
    )

    assert "CUDA_VISIBLE_DEVICES=0,1" in cmd


def test_build_sbatch_script():
    machine = MachineCapsule(
        machine_id="m1",
        name="M1",
        env=EnvSpec(kind=EnvKind.conda, conda_env="ar"),
        workdir="/runs",
    )
    script = build_sbatch_script(machine, "run1", "python train.py", [0])

    assert script.startswith("#!/bin/bash")
    assert "--gres=gpu:1" in script
    assert "autoresearch-run1" in script
