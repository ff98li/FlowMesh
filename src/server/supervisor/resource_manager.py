import os
import re
import shutil
import subprocess
from enum import StrEnum
from typing import Any

from docker import DockerClient
from docker.types import DeviceRequest
from pydantic import BaseModel

from .. import env
from ..utils.helpers import get_docker_client

_MIG_UUID_RE = re.compile(r"^MIG-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


class GpuArch(StrEnum):
    BLACKWELL = "blackwell"
    HOPPER = "hopper"
    UNKNOWN = "unknown"

    @classmethod
    def from_name(cls, name: str) -> "GpuArch":
        name = name.strip().lower()
        blackwell_pattern = r"(rtx50|5090|5080|5070|b100|b200|gb200|gb100|blackwell)"
        if re.search(blackwell_pattern, name):
            return cls.BLACKWELL
        hopper_pattern = r"(h100|h800|h200|hopper)"
        if re.search(hopper_pattern, name):
            return cls.HOPPER
        return cls.UNKNOWN


class MachineEnv(BaseModel):
    cpu_count: int
    gpu_families: dict[int, GpuArch]
    gpu_tokens: dict[int, str]
    available_gpus: set[int]

    @property
    def gpu_count(self) -> int:
        return len(self.gpu_families)


class ResourceManager:
    _instance: "ResourceManager | None" = None

    def __init__(self) -> None:
        self._docker_client: DockerClient | None
        try:
            self._docker_client = get_docker_client()
        except Exception:
            # No Docker on this host: fall back to host-level probing so the
            # native worker provider still works.
            self._docker_client = None
        self._env = self._detect_machine_env()

    @classmethod
    def get_instance(cls) -> "ResourceManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def total_gpu_count(self) -> int:
        return self._env.gpu_count

    def available_gpu_count(self) -> int:
        return len(self._env.available_gpus)

    def get_gpu_tokens(self, devices: list[int]) -> list[str]:
        """Return parent-allocation tokens for allocation-relative slots."""
        try:
            return [self._env.gpu_tokens[device] for device in devices]
        except KeyError as exc:
            raise ValueError(f"Unknown GPU allocation slot: {exc.args[0]}") from exc

    def reserve_gpus(
        self, devices: list[int] | None = None, n: int | None = None
    ) -> tuple[list[int], GpuArch]:
        """Atomically reserve GPUs and return their indices and architecture.

        Either ``devices`` (validate that the explicit set is free) or ``n``
        (auto-pick the lowest N free indices) must be given, not both.
        Selection, arch-consistency check, and removal from the available set
        run as one synchronous block, so concurrent callers on the same event
        loop never observe the same indices.

        Note: the atomicity guarantee is per event loop, not across threads —
        callers must invoke this from the supervisor's main loop thread (do
        not wrap in ``asyncio.to_thread`` or call from a worker thread).
        """
        if (n is None) == (devices is None):
            raise ValueError("Provide exactly one of n or devices")

        available_gpus = self._env.available_gpus
        # Pick devices
        if devices is not None:
            if not devices:
                raise ValueError("Empty device list")
            invalid = [d for d in devices if d not in available_gpus]
            if invalid:
                raise ValueError(f"Requested GPUs are not available: {invalid}")
            picked = devices.copy()
        else:
            assert n is not None
            if n <= 0:
                raise ValueError("Invalid number of GPUs")
            if n > len(available_gpus):
                raise ValueError("Not enough available GPUs")
            picked = [min(available_gpus)] if n == 1 else sorted(available_gpus)[:n]

        # Check architecture consistency
        archs = {self._env.gpu_families[d] for d in picked}
        if len(archs) != 1:
            raise ValueError("Selected CUDA devices have different architectures.")
        arch = archs.pop()

        available_gpus.difference_update(picked)
        return picked, arch

    def deallocate_gpus(self, devices: list[int]) -> None:
        self._env.available_gpus.update(devices)

    def _detect_machine_env(self) -> MachineEnv:
        cpu_count = os.cpu_count() or 0
        if self._docker_client is not None:
            try:
                cpu_count = self._docker_client.info().get("NCPU", cpu_count)
            except Exception:
                pass

        inventory = self._probe_gpu_inventory()
        allocation_tokens = self._allocation_tokens(inventory)
        gpu_families: dict[int, GpuArch] = {}
        gpu_tokens: dict[int, str] = {}
        available_gpus: set[int] = set()

        for slot, token in enumerate(allocation_tokens):
            gpu_tokens[slot] = token
            gpu_families[slot] = self._arch_for_token(token, inventory)
            available_gpus.add(slot)

        return MachineEnv(
            cpu_count=cpu_count,
            gpu_families=gpu_families,
            gpu_tokens=gpu_tokens,
            available_gpus=available_gpus,
        )

    def _probe_gpu_inventory(self) -> list[tuple[int, str, str]]:
        try:
            if self._docker_client is not None:
                optional_kwargs: dict[str, Any] = {}
                if env.DOCKER_GPU_RUNTIME is not None:
                    optional_kwargs["runtime"] = env.DOCKER_GPU_RUNTIME
                raw_output = self._docker_client.containers.run(
                    image=env.SERVER_CUDA_PROBE_IMAGE,
                    device_requests=[DeviceRequest(count=-1, capabilities=[["gpu"]])],
                    command=(
                        "nvidia-smi --query-gpu=index,uuid,name "
                        "--format=csv,noheader"
                    ),
                    remove=True,
                    **optional_kwargs,
                )
                output = raw_output.decode("utf-8").strip()
            else:
                nvidia_smi = shutil.which("nvidia-smi")
                if nvidia_smi is None:
                    return []
                # The executable is resolved to an absolute trusted utility path.
                result = subprocess.run(  # nosec B603
                    [
                        nvidia_smi,
                        "--query-gpu=index,uuid,name",
                        "--format=csv,noheader",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                output = result.stdout.strip() if result.returncode == 0 else ""
        except Exception:
            return []

        inventory: list[tuple[int, str, str]] = []
        for line in output.splitlines():
            fields = [field.strip() for field in line.split(",", maxsplit=2)]
            if len(fields) != 3:
                continue
            try:
                index = int(fields[0])
            except ValueError:
                continue
            inventory.append((index, fields[1], fields[2]))
        return inventory

    @staticmethod
    def _allocation_tokens(inventory: list[tuple[int, str, str]]) -> list[str]:
        raw = env.CUDA_VISIBLE_DEVICES
        if raw is None:
            return [str(index) for index, _, _ in sorted(inventory)]
        tokens = [token.strip() for token in raw.split(",") if token.strip()]
        if not inventory or len(tokens) != len(set(tokens)):
            return []
        inventory_indices = {index for index, _, _ in inventory}
        inventory_uuids = {uuid for _, uuid, _ in inventory if uuid}
        non_mig_count = 0
        for token in tokens:
            if token.isdecimal():
                if int(token) not in inventory_indices:
                    return []
                non_mig_count += 1
                continue
            if token.startswith("GPU-"):
                if token not in inventory_uuids:
                    return []
                non_mig_count += 1
                continue
            if token.startswith("MIG-GPU-"):
                if not any(uuid in token for uuid in inventory_uuids):
                    return []
                continue
            # Recent drivers use opaque MIG UUIDs that do not contain their
            # parent GPU UUID. A successful inventory probe plus the strict
            # prefix is the strongest portable validation available here.
            if _MIG_UUID_RE.fullmatch(token):
                continue
            return []
        if non_mig_count > len(inventory):
            return []
        return tokens

    @staticmethod
    def _arch_for_token(token: str, inventory: list[tuple[int, str, str]]) -> GpuArch:
        for index, uuid, name in inventory:
            if token == str(index) or token == uuid or uuid in token:
                return GpuArch.from_name(name)
        return GpuArch.UNKNOWN
