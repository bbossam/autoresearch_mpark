"""Execution-layer helpers for remote machines (SSH + Slurm).

The nvidia-smi parser and the command/script builders are pure and tested.
``probe_machine`` is the thin side-effecting part — it shells out over SSH.
"""

from __future__ import annotations

import shlex
import subprocess

from .agents.resource import GpuInfo, MachineState
from .models import EnvKind, EnvSpec, MachineCapsule

NVIDIA_SMI_QUERY = (
    "nvidia-smi --query-gpu=index,memory.total,memory.free,utilization.gpu "
    "--format=csv,noheader,nounits"
)


def parse_nvidia_smi(text: str) -> list[GpuInfo]:
    """Parse ``nvidia-smi`` CSV output into GpuInfo records."""
    gpus: list[GpuInfo] = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 4:
            continue
        try:
            index, total, free, util = (int(float(p)) for p in parts)
        except ValueError:
            continue
        gpus.append(
            GpuInfo(
                index=index,
                mem_total_mb=total,
                mem_free_mb=free,
                util_pct=util,
            )
        )
    return gpus


def env_prefix(env: EnvSpec) -> list[str]:
    """Shell tokens that wrap an experiment command to run inside the env."""
    if env.kind == EnvKind.docker:
        return ["docker", "run", "--rm", "--gpus", "all", env.image, "bash", "-lc"]
    return ["conda", "run", "-n", env.conda_env, "bash", "-lc"]


def build_run_command(
    env: EnvSpec, command: str, gpu_indices: list[int]
) -> str:
    """Full shell command: pin GPUs, then run ``command`` inside the env."""
    inner = command
    if gpu_indices:
        devices = ",".join(str(i) for i in gpu_indices)
        inner = f"CUDA_VISIBLE_DEVICES={devices} {command}"
    prefix = " ".join(shlex.quote(token) for token in env_prefix(env))
    return f"{prefix} {shlex.quote(inner)}"


def build_sbatch_script(
    machine: MachineCapsule,
    run_id: str,
    command: str,
    gpu_indices: list[int],
) -> str:
    """A Slurm batch script running ``command`` inside the machine's env."""
    gpus = max(1, len(gpu_indices))
    return "\n".join(
        [
            "#!/bin/bash",
            f"#SBATCH --job-name=autoresearch-{run_id}",
            f"#SBATCH --gres=gpu:{gpus}",
            f"#SBATCH --output={run_id}.slurm.out",
            f"#SBATCH --chdir={machine.workdir}",
            "",
            build_run_command(machine.env, command, gpu_indices),
            "",
        ]
    )


def _parse_disk_gb(text: str) -> float:
    for token in text.replace("G", " ").split():
        try:
            return float(token)
        except ValueError:
            continue
    return 0.0


def probe_machine(machine: MachineCapsule, *, timeout: float = 30.0) -> MachineState:
    """Query a machine's GPU and disk state over SSH (side-effecting).

    Returns an unreachable MachineState rather than raising, so probing a fleet
    never aborts on one dead host.
    """
    probe = (
        f"{NVIDIA_SMI_QUERY}; echo '---'; "
        f"df -BG --output=avail {shlex.quote(machine.workdir)} | tail -1"
    )
    if machine.ssh_target:
        argv = ["ssh", "-o", "BatchMode=yes", machine.ssh_target, probe]
    else:
        argv = ["bash", "-lc", probe]
    try:
        proc = subprocess.run(
            argv, text=True, capture_output=True, timeout=timeout
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return MachineState(
            machine_id=machine.machine_id, reachable=False, note=str(exc)
        )
    if proc.returncode != 0:
        return MachineState(
            machine_id=machine.machine_id,
            reachable=False,
            note=proc.stderr.strip() or f"exit code {proc.returncode}",
        )
    smi_part, _, disk_part = proc.stdout.partition("---")
    return MachineState(
        machine_id=machine.machine_id,
        reachable=True,
        gpus=parse_nvidia_smi(smi_part),
        disk_free_gb=_parse_disk_gb(disk_part),
    )
