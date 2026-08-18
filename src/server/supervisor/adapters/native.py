import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ...hooks import PrincipalContext
from ..resource_manager import GpuArch, ResourceManager
from ..schemas import WorkerHardware, WorkerInfo, WorkerStatus
from .base import (
    ProviderSpec,
    WorkerAdapter,
    WorkerConfig,
    WorkerFactory,
    WorkerTokenType,
)

_STOP_TIMEOUT = 30  # seconds
_PROVIDER_NAME = "native"
_HW_PROBE_PREFIX = "HW_PROBE_OUTPUT: "
_START_GRACE_SECONDS = 1.5

logger = logging.getLogger("supervisor")


class WorkerType(StrEnum):
    CPU = "cpu"
    GPU = "gpu"


class NativeWorkerConfig(WorkerConfig):
    worker_type: WorkerType = WorkerType.CPU
    """Type of worker (cpu or gpu)"""
    cuda_devices: list[int] | None = None
    """List of CUDA devices to use (if any)"""
    gpu_count: int = 1
    """Number of GPUs to auto-pick when ``cuda_devices`` is unset
    (only consulted for GPU workers)."""
    command: list[str] | None = None
    """Worker process command. Defaults to ``[sys.executable, -m, worker.main]``."""
    cwd: str | None = None
    """Working directory for the worker process (defaults to the
    supervisor's working directory)."""
    log_dir: str | None = None
    """Directory for worker stdout/stderr logs (defaults to the heartbeat
    file directory)."""

    def model_post_init(self, __context: object) -> None:
        super().model_post_init(__context)
        if self.worker_type == WorkerType.GPU and (
            isinstance(self.cuda_devices, list) and len(self.cuda_devices) == 0
        ):
            raise ValueError("Expected at least one CUDA device for GPU worker.")


class NativeWorkerAdapter(WorkerAdapter):
    """Runs a FlowMesh worker as a native OS process (no containers)."""

    def __init__(
        self,
        token: WorkerTokenType,
        name: str,
        command: list[str],
        cuda_devices: list[int] | None,
        gpu_arch: GpuArch | None,
        config: NativeWorkerConfig,
        owner: PrincipalContext,
    ) -> None:
        if config.worker_type == WorkerType.GPU and (
            cuda_devices is None or len(cuda_devices) == 0
        ):
            raise ValueError("Expected at least one CUDA device for GPU worker.")

        super().__init__(token, name, config, owner)

        self.config: NativeWorkerConfig
        self.command = command
        self.cuda_devices = cuda_devices
        self.gpu_arch = gpu_arch

        self._proc: subprocess.Popen[bytes] | None = None
        self._status: WorkerStatus = WorkerStatus.STOPPED
        self._hardware: WorkerHardware | dict[str, Any] | None = None

    @property
    def status(self) -> WorkerStatus:
        return self._status

    def set_status(self, status: WorkerStatus) -> None:
        self._status = status

    def get_info(self) -> WorkerInfo:
        hardware = self._hardware
        if isinstance(hardware, dict):
            hardware = WorkerHardware.model_validate(hardware)
            self._hardware = hardware
        return WorkerInfo(
            id=self.worker_id,
            name=self.name,
            provider=_PROVIDER_NAME,
            status=self.status,
            hardware=hardware,
        )

    async def start(self) -> bool:
        self.set_status(WorkerStatus.STARTING)
        try:
            ok = await asyncio.to_thread(self._start)
            if not ok:
                self.set_status(WorkerStatus.STOPPED)
            return ok
        except Exception:
            self.set_status(WorkerStatus.STOPPED)
            raise

    async def prepare(self) -> None:
        self._hardware = await asyncio.to_thread(self._probe_hardware)

    async def stop(self) -> bool:
        prev_status = self.status
        if prev_status in (WorkerStatus.STOPPING, WorkerStatus.STOPPED):
            return True
        self.set_status(WorkerStatus.STOPPING)
        try:
            ok = await asyncio.to_thread(self._stop)
            if not ok:
                self.set_status(prev_status)
            return ok
        except Exception:
            self.set_status(prev_status)
            raise

    def _log_path(self) -> str:
        log_dir = self.config.log_dir
        if not log_dir:
            hb_file = self.config.hb_file or os.path.join(
                os.environ.get("WORKER_HB_DIR", "/tmp"), f"{self.token}.hb"
            )
            log_dir = os.path.dirname(hb_file) or "/tmp"
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, f"{self.name}.log")

    def _environment(self) -> dict[str, str]:
        environment = self._base_environment()
        # FlowMesh installs no packages (setuptools packages=[]); the worker
        # process resolves `shared`/`worker` imports via PYTHONPATH=src.
        src_dir = str(Path(__file__).resolve().parents[3])
        existing = os.environ.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing}".rstrip(
            os.pathsep
        )
        if self.config.worker_type == WorkerType.GPU:
            assert self.cuda_devices is not None
            assert self.gpu_arch is not None
            gpu_ids = ",".join(str(i) for i in self.cuda_devices)
            environment["CUDA_VISIBLE_DEVICES"] = gpu_ids
            environment["WORKER_HOST_GPU_ID"] = gpu_ids
            environment["WORKER_HOST_GPU_ARCH"] = self.gpu_arch.value
        else:
            # Hide host GPUs from CPU workers so the scheduler cannot route
            # GPU tasks onto them. NVML ignores CUDA_VISIBLE_DEVICES, so the
            # hardware collector is disabled explicitly.
            environment["CUDA_VISIBLE_DEVICES"] = ""
            environment["FLOWMESH_COLLECT_GPU"] = "0"
        return environment

    def _start(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            logger.warning("Worker process %s is already running.", self.name)
            return True

        cmd = self.command or [sys.executable, "-m", "worker.main"]
        log_path = self._log_path()
        log_file = open(log_path, "ab")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.config.cwd,
                env={**os.environ, **self._environment()},
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception as exc:
            log_file.close()
            logger.error(
                "Failed to start native worker %s: %s", self.name, repr(exc)
            )
            return False

        self._proc = proc
        time.sleep(_START_GRACE_SECONDS)
        if proc.poll() is not None:
            log_file.close()
            logger.error(
                "Native worker %s exited immediately (rc=%s); log: %s",
                self.name,
                proc.returncode,
                log_path,
            )
            return False
        log_file.close()

        if self._hardware is None:
            self._hardware = self._probe_hardware()
        return True

    def _stop(self) -> bool:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            self._proc = None
            return True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            self._proc = None
            return True
        except Exception as exc:
            logger.error("Failed to signal native worker %s: %s", self.name, repr(exc))
            return False
        try:
            proc.wait(timeout=_STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            logger.warning(
                "Native worker %s did not stop within %ss; killing it.",
                self.name,
                _STOP_TIMEOUT,
            )
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
            proc.wait(timeout=10)
        self._proc = None
        return True

    def _probe_hardware(self) -> dict[str, Any] | None:
        cmd = [sys.executable, "-m", "worker.main", "--collect-hw"]
        bandwidth = self.config.network_bandwidth
        if bandwidth is not None:
            cmd.extend(["--bandwidth-bytes-per-sec", str(bandwidth)])
        cmd.extend(["--collect-hw-prefix", _HW_PROBE_PREFIX])
        try:
            result = subprocess.run(
                cmd,
                cwd=self.config.cwd,
                env={**os.environ, **self._environment()},
                capture_output=True,
                timeout=120,
            )
        except Exception as exc:
            logger.warning(
                "Failed to run hardware probe for worker %s: %s",
                self.name,
                repr(exc),
            )
            return None
        output = result.stdout or result.stderr or b""
        return self._parse_hardware_output(output, _HW_PROBE_PREFIX)

    @staticmethod
    def _parse_hardware_output(
        output: bytes | str | None, prefix: str | None
    ) -> dict[str, Any] | None:
        if output is None:
            return None
        if isinstance(output, (bytes, bytearray)):
            output_text = output.decode("utf-8", errors="replace").strip()
        else:
            output_text = str(output).strip()
        if not output_text:
            logger.warning("Hardware probe returned no output")
            return None
        if prefix:
            for line in output_text.splitlines():
                if line.startswith(prefix):
                    output_text = line.removeprefix(prefix)
                    break
        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid hardware probe output: %s", repr(exc))
            return None
        return payload if isinstance(payload, dict) else None


class NativeWorkerFactory(WorkerFactory):
    _NAME_PREFIXES = {
        WorkerType.CPU: "native_worker_cpu_",
        WorkerType.GPU: "native_worker_gpu_",
    }

    def __init__(self, system_principal: PrincipalContext) -> None:
        super().__init__(system_principal)
        self._rm = ResourceManager.get_instance()
        self._name_counter: Counter[str] = Counter()

    def create_worker(
        self, token: WorkerTokenType, config: NativeWorkerConfig
    ) -> NativeWorkerAdapter:
        cuda_devices: list[int] | None
        gpu_arch: GpuArch | None
        match config.worker_type:
            case WorkerType.CPU:
                cuda_devices = gpu_arch = None
            case WorkerType.GPU:
                cuda_devices, gpu_arch = self._rm.reserve_gpus(
                    devices=config.cuda_devices,
                    n=config.gpu_count if config.cuda_devices is None else None,
                )
            case _:
                raise ValueError(f"Unsupported worker type: {config.worker_type}")

        name = config.worker_alias or self._next_name(config.worker_type)
        return NativeWorkerAdapter(
            token=token,
            name=name,
            command=list(config.command) if config.command else [],
            cuda_devices=cuda_devices,
            gpu_arch=gpu_arch,
            config=config,
            owner=self.system_principal,
        )

    def destroy_worker(self, worker: WorkerAdapter) -> None:
        if not isinstance(worker, NativeWorkerAdapter):
            raise ValueError("Invalid worker type")
        if worker.cuda_devices:
            self._rm.deallocate_gpus(worker.cuda_devices)

    def _next_name(self, worker_type: WorkerType) -> str:
        prefix = self._NAME_PREFIXES[worker_type]
        index = self._name_counter[prefix]
        self._name_counter[prefix] = index + 1
        return f"{prefix}{index}"


def get_provider_spec(system_principal: PrincipalContext) -> ProviderSpec:
    return ProviderSpec(
        name=_PROVIDER_NAME,
        config_cls=NativeWorkerConfig,
        adapter_cls=NativeWorkerAdapter,
        factory=NativeWorkerFactory(system_principal),
    )
