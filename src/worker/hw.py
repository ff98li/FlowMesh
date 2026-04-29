# worker/hw.py
"""Hardware introspection helpers.

Collects lightweight CPU/memory/GPU/network information for registration.
"""

import os
import platform
import re
import socket
import subprocess
import sys

from shared.tasks.worker_message import (
    CPUInfo,
    GpuInfo,
    GpuPlatformInfo,
    MemoryInfo,
    NetworkInfo,
    WorkerHardware,
)


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def collect_hw(*, bandwidth_bytes_per_sec: float | None = None) -> WorkerHardware:
    # CPU
    cpu = CPUInfo(
        logical_cores=os.cpu_count() or 0,
        model=platform.processor() or platform.machine(),
    )
    # Memory
    mem = MemoryInfo(total_bytes=None)
    if sys.platform.startswith("linux") and os.path.exists("/proc/meminfo"):
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem.total_bytes = int(line.split()[1]) * 1024
                    break
    # GPU (NVIDIA)
    full = _run(["nvidia-smi"])  # presence indicates NVIDIA stack
    cuda = None
    drv = None
    m = re.search(r"CUDA Version:\s*([\w\.\-]+)", full)
    cuda = m.group(1) if m else None
    m = re.search(r"Driver Version:\s*([\w\.\-]+)", full)
    drv = m.group(1) if m else None
    lst = _run(["nvidia-smi", "-L"]) if full else ""
    mem_listing = (
        _run(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.total",
                "--format=csv,noheader,nounits",
            ]
        )
        if full
        else ""
    )
    memory_map: dict[int, int | None] = {}
    for line in mem_listing.splitlines():
        parts = [segment.strip() for segment in line.split(",") if segment is not None]
        if len(parts) < 2:
            continue
        try:
            idx = int(parts[0])
            mem_mb = float(parts[1])
        except (ValueError, TypeError):
            continue
        if mem_mb <= 0:
            memory_map[idx] = None
            continue
        memory_map[idx] = int(mem_mb * 1024 * 1024)
    gpus: list[GpuInfo] = []
    for line in lst.splitlines():
        m = re.match(r"GPU\s+(\d+):\s+(.+?)\s+\(UUID:\s*([^\)]+)\)", line.strip())
        if m:
            idx = int(m.group(1))
            gpus.append(
                GpuInfo(
                    index=idx,
                    name=m.group(2),
                    uuid=m.group(3),
                    memory_total_bytes=memory_map.get(idx),
                )
            )
    gpu = GpuPlatformInfo(driver_version=drv, cuda_version=cuda, gpus=gpus)

    # Network
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = None
    network = NetworkInfo(ip=ip, bandwidth_bytes_per_sec=bandwidth_bytes_per_sec)

    return WorkerHardware(cpu=cpu, memory=mem, gpu=gpu, network=network)
