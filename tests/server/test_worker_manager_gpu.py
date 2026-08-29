"""Tests for server GPU resource management and worker capacity reporting."""

import asyncio
import logging
from collections import Counter
from unittest.mock import AsyncMock, MagicMock

import pytest

from server import env
from server.hooks import PrincipalContext
from server.supervisor.adapters.base import WorkerTokenType
from server.supervisor.adapters.docker import (
    DockerWorkerAdapter,
    DockerWorkerConfig,
    DockerWorkerFactory,
    WorkerType,
)
from server.supervisor.manager import WorkerInitConfig, WorkerManager
from server.supervisor.resource_manager import GpuArch, MachineEnv, ResourceManager
from server.supervisor.schemas import WorkerStatus

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _resource_manager(available: set[int]) -> ResourceManager:
    """Build a ResourceManager with a fixed set of available GPU indices."""
    rm = object.__new__(ResourceManager)
    rm._env = MachineEnv(
        cpu_count=16,
        gpu_families={i: GpuArch.UNKNOWN for i in available},
        gpu_tokens={i: str(i) for i in available},
        available_gpus=set(available),
    )
    return rm


def _worker_manager() -> WorkerManager:
    """Construct a WorkerManager in started state without filesystem or Docker."""
    wm = object.__new__(WorkerManager)
    wm.config_path = "/dev/null"
    wm.logger = logging.getLogger("test-wm")
    wm._registry = MagicMock()
    wm._is_started = True
    wm._default_worker_config = {}
    wm._capacity_change_callback = None
    return wm


# ------------------------------------------------------------------ #
# ResourceManager.reserve_gpus
# ------------------------------------------------------------------ #


class TestReserveGpusByCount:
    def test_single_gpu_returns_lowest_index_and_reserves(self) -> None:
        rm = _resource_manager({0, 1, 2, 3})
        devices, _ = rm.reserve_gpus(n=1)
        assert devices == [0]
        assert rm.available_gpu_count() == 3
        assert 0 not in rm._env.available_gpus

    def test_single_gpu_picks_minimum_when_indices_nonzero(self) -> None:
        rm = _resource_manager({2, 3})
        devices, _ = rm.reserve_gpus(n=1)
        assert devices == [2]

    def test_two_gpus_returns_two_lowest_sorted(self) -> None:
        rm = _resource_manager({0, 1, 2, 3})
        devices, _ = rm.reserve_gpus(n=2)
        assert devices == [0, 1]
        assert rm.available_gpu_count() == 2

    def test_two_gpus_sparse_indices(self) -> None:
        rm = _resource_manager({1, 3})
        devices, _ = rm.reserve_gpus(n=2)
        assert devices == [1, 3]

    def test_four_gpus_returns_all_sorted(self) -> None:
        rm = _resource_manager({0, 1, 2, 3})
        devices, _ = rm.reserve_gpus(n=4)
        assert devices == [0, 1, 2, 3]
        assert rm.available_gpu_count() == 0

    def test_requesting_more_than_available_raises(self) -> None:
        rm = _resource_manager({0, 1})
        with pytest.raises(ValueError, match="Not enough available GPUs"):
            rm.reserve_gpus(n=3)
        assert rm.available_gpu_count() == 2

    def test_zero_raises(self) -> None:
        rm = _resource_manager({0, 1})
        with pytest.raises(ValueError, match="Invalid number of GPUs"):
            rm.reserve_gpus(n=0)

    def test_negative_raises(self) -> None:
        rm = _resource_manager({0, 1})
        with pytest.raises(ValueError, match="Invalid number of GPUs"):
            rm.reserve_gpus(n=-1)


class TestReserveGpusByDevices:
    def test_explicit_devices_reserve_and_remove(self) -> None:
        rm = _resource_manager({0, 1, 2, 3})
        devices, _ = rm.reserve_gpus(devices=[1, 2])
        assert devices == [1, 2]
        assert rm._env.available_gpus == {0, 3}

    def test_unavailable_device_raises(self) -> None:
        rm = _resource_manager({0, 1})
        with pytest.raises(ValueError, match="Requested GPUs are not available"):
            rm.reserve_gpus(devices=[5])
        assert rm.available_gpu_count() == 2

    def test_partially_unavailable_raises_without_partial_reserve(self) -> None:
        rm = _resource_manager({0, 1})
        with pytest.raises(ValueError, match="Requested GPUs are not available"):
            rm.reserve_gpus(devices=[0, 5])
        assert rm._env.available_gpus == {0, 1}

    def test_empty_device_list_raises(self) -> None:
        rm = _resource_manager({0, 1})
        with pytest.raises(ValueError, match="Empty device list"):
            rm.reserve_gpus(devices=[])


class TestReserveGpusArgs:
    def test_neither_arg_raises(self) -> None:
        rm = _resource_manager({0, 1})
        with pytest.raises(ValueError, match="exactly one of n or devices"):
            rm.reserve_gpus()

    def test_both_args_raises(self) -> None:
        rm = _resource_manager({0, 1})
        with pytest.raises(ValueError, match="exactly one of n or devices"):
            rm.reserve_gpus(n=1, devices=[0])


class TestReserveGpusAtomicity:
    def test_repeated_calls_yield_disjoint_devices(self) -> None:
        rm = _resource_manager({0, 1, 2, 3})
        d1, _ = rm.reserve_gpus(n=2)
        d2, _ = rm.reserve_gpus(n=2)
        assert set(d1).isdisjoint(d2)
        assert sorted(d1 + d2) == [0, 1, 2, 3]
        assert rm.available_gpu_count() == 0

    def test_mixed_arch_raises(self) -> None:
        rm = object.__new__(ResourceManager)
        rm._env = MachineEnv(
            cpu_count=16,
            gpu_families={0: GpuArch.HOPPER, 1: GpuArch.BLACKWELL},
            gpu_tokens={0: "GPU-hopper", 1: "MIG-blackwell"},
            available_gpus={0, 1},
        )
        with pytest.raises(ValueError, match="different architectures"):
            rm.reserve_gpus(devices=[0, 1])
        # No partial reservation on failure.
        assert rm._env.available_gpus == {0, 1}


class TestAvailableGpuCount:
    def test_four_gpus(self) -> None:
        assert _resource_manager({0, 1, 2, 3}).available_gpu_count() == 4

    def test_two_gpus(self) -> None:
        assert _resource_manager({0, 1}).available_gpu_count() == 2

    def test_no_gpus(self) -> None:
        assert _resource_manager(set()).available_gpu_count() == 0


class TestAllocationTokens:
    def test_tokens_are_opaque_and_allocation_relative(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            env,
            "CUDA_VISIBLE_DEVICES",
            "GPU-first,MIG-GPU-parent/2/0",
        )

        tokens = ResourceManager._allocation_tokens(
            [(3, "GPU-first", "NVIDIA H100"), (7, "GPU-parent", "NVIDIA H100")]
        )

        assert tokens == ["GPU-first", "MIG-GPU-parent/2/0"]

    @pytest.mark.parametrize("raw", ["-1", "999", "not-a-gpu", "GPU-unknown"])
    def test_invalid_allocation_token_fails_closed(
        self, raw: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(env, "CUDA_VISIBLE_DEVICES", raw)

        assert (
            ResourceManager._allocation_tokens([(0, "GPU-known", "NVIDIA H100")]) == []
        )

    def test_explicit_allocation_fails_closed_when_probe_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(env, "CUDA_VISIBLE_DEVICES", "0")

        assert ResourceManager._allocation_tokens([]) == []

    def test_reserved_slots_map_back_to_parent_tokens(self) -> None:
        rm = object.__new__(ResourceManager)
        rm._env = MachineEnv(
            cpu_count=16,
            gpu_families={0: GpuArch.HOPPER, 1: GpuArch.BLACKWELL},
            gpu_tokens={0: "GPU-first", 1: "MIG-GPU-parent/2/0"},
            available_gpus={0, 1},
        )

        devices, _ = rm.reserve_gpus(devices=[1])

        assert devices == [1]
        assert rm.get_gpu_tokens(devices) == ["MIG-GPU-parent/2/0"]

    def test_architecture_lookup_accepts_uuid_and_mig_parent_uuid(self) -> None:
        inventory = [(3, "GPU-parent", "NVIDIA H100")]

        assert (
            ResourceManager._arch_for_token("GPU-parent", inventory) is GpuArch.HOPPER
        )
        assert (
            ResourceManager._arch_for_token("MIG-GPU-parent/2/0", inventory)
            is GpuArch.HOPPER
        )


class TestMachineEnvDetection:
    def test_gpu_probe_uses_configured_cuda_image(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rm = object.__new__(ResourceManager)
        containers = MagicMock()
        containers.run.return_value = b"0, GPU-h100, NVIDIA H100\n"
        rm._docker_client = MagicMock()
        rm._docker_client.info.return_value = {"NCPU": 32}
        rm._docker_client.containers = containers

        monkeypatch.setattr(env, "SERVER_CUDA_PROBE_IMAGE", "example/probe:arm64")
        monkeypatch.setattr(env, "CUDA_VISIBLE_DEVICES", None)

        detected = rm._detect_machine_env()

        assert detected.cpu_count == 32
        assert detected.available_gpus == {0}
        assert detected.gpu_families == {0: GpuArch.HOPPER}
        assert detected.gpu_tokens == {0: "0"}
        containers.run.assert_called_once()
        assert containers.run.call_args.kwargs["image"] == "example/probe:arm64"
        assert "runtime" not in containers.run.call_args.kwargs

    def test_gpu_probe_uses_runtime_override_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rm = object.__new__(ResourceManager)
        containers = MagicMock()
        containers.run.return_value = b"0, GPU-h100, NVIDIA H100\n"
        rm._docker_client = MagicMock()
        rm._docker_client.info.return_value = {"NCPU": 32}
        rm._docker_client.containers = containers

        monkeypatch.setattr(env, "SERVER_CUDA_PROBE_IMAGE", "example/probe:legacy")
        monkeypatch.setattr(env, "DOCKER_GPU_RUNTIME", "nvidia")
        monkeypatch.setattr(env, "CUDA_VISIBLE_DEVICES", None)

        detected = rm._detect_machine_env()

        assert detected.available_gpus == {0}
        assert containers.run.call_args.kwargs["runtime"] == "nvidia"


class TestDockerWorkerRuntimeSelection:
    def _worker(self) -> DockerWorkerAdapter:
        worker = object.__new__(DockerWorkerAdapter)
        worker.config = DockerWorkerConfig(worker_type=WorkerType.GPU, cuda_devices=[3])
        worker.token = "worker-token"  # type: ignore[assignment]
        worker.owner = PrincipalContext(
            principal_id="test-user",
            org_id="test-org",
            external_id="test-user",
            principal_type="user",
            scopes=[],
        )
        worker.container_name = "worker-gpu-3"
        worker.cuda_devices = [3]
        worker.cuda_device_tokens = ["3"]
        worker.gpu_arch = GpuArch.BLACKWELL
        return worker

    def test_gpu_worker_omits_runtime_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        worker = self._worker()
        monkeypatch.setattr(env, "DOCKER_GPU_RUNTIME", None)

        environment: dict[str, str] = {}
        labels: dict[str, str] = {}

        device_requests, runtime = worker._apply_worker_type_settings(
            environment, labels
        )

        assert runtime is None
        assert device_requests is not None
        assert environment["CUDA_VISIBLE_DEVICES"] == "0"
        assert environment["WORKER_HOST_GPU_ID"] == "3"
        assert environment["WORKER_HOST_GPU_ARCH"] == GpuArch.BLACKWELL.value
        assert labels["flowmesh.worker.gpu_id"] == "3"

    def test_gpu_worker_uses_parent_allocation_token(self) -> None:
        worker = self._worker()
        worker.cuda_devices = [0]
        worker.cuda_device_tokens = ["MIG-GPU-parent/1/0"]

        environment: dict[str, str] = {}
        device_requests, _ = worker._apply_worker_type_settings(environment, {})

        assert device_requests is not None
        assert device_requests[0].device_ids == ["MIG-GPU-parent/1/0"]
        assert environment["CUDA_VISIBLE_DEVICES"] == "0"
        assert environment["WORKER_HOST_GPU_ID"] == "MIG-GPU-parent/1/0"

    def test_gpu_worker_uses_runtime_override_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        worker = self._worker()
        monkeypatch.setattr(env, "DOCKER_GPU_RUNTIME", "nvidia")

        device_requests, runtime = worker._apply_worker_type_settings({}, {})

        assert runtime == "nvidia"
        assert device_requests is not None

    def test_worker_environment_passes_runtime_override_to_worker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        worker = self._worker()
        monkeypatch.setattr(env, "DOCKER_GPU_RUNTIME", "nvidia")

        environment = worker._base_environment()

        assert environment["DOCKER_GPU_RUNTIME"] == "nvidia"


def test_docker_worker_alias_does_not_control_container_identity() -> None:
    factory = object.__new__(DockerWorkerFactory)
    factory.system_principal = PrincipalContext(
        principal_id="test-user",
        org_id="test-org",
        external_id="test-user",
        principal_type="user",
        scopes=[],
    )
    factory._rm = MagicMock()
    factory._docker = MagicMock()
    factory._docker.containers.list.return_value = []
    factory._worker_id_registry = Counter()

    worker = factory.create_worker(
        WorkerTokenType("worker-token"),
        DockerWorkerConfig(worker_alias="unrelated-stopped-container"),
    )

    assert worker.name == "unrelated-stopped-container"
    assert worker.container_name == "flowmesh_server_worker_cpu_0"


class TestCapacityChangeReporting:
    def _run(self, coro: object) -> object:  # type: ignore[return]
        return asyncio.run(coro)  # type: ignore[arg-type]

    def test_create_worker_reports_capacity_change(self) -> None:
        wm = _worker_manager()
        callback = MagicMock()
        wm._capacity_change_callback = callback

        worker = MagicMock()
        info = MagicMock()
        worker.name = "w-1"
        worker.get_info.return_value = info
        wm._create_worker = MagicMock(return_value=worker)  # type: ignore[method-assign]
        wm._start_worker = AsyncMock(return_value=True)  # type: ignore[method-assign]

        result = self._run(
            wm.create_worker(
                WorkerInitConfig(
                    provider="docker", init_on_start=True, worker_config={}
                )
            )
        )

        assert result is info
        callback.assert_called_once_with()

    def test_destroy_worker_reports_capacity_change(self) -> None:
        wm = _worker_manager()
        callback = MagicMock()
        wm._capacity_change_callback = callback

        worker = MagicMock()
        worker.name = "w-1"
        wm._registry.try_get_by_name.return_value = worker  # type: ignore[attr-defined]
        wm._registry.try_pop_by_name = MagicMock()  # type: ignore[attr-defined, method-assign]
        wm._stop_and_destroy_worker = AsyncMock(return_value=True)  # type: ignore[method-assign]

        result = self._run(wm.destroy_worker("w-1"))

        assert result is True
        callback.assert_called_once_with()

    def test_failed_destroy_keeps_registry_and_capacity(self) -> None:
        wm = _worker_manager()
        callback = MagicMock()
        wm._capacity_change_callback = callback
        worker = MagicMock()
        worker.name = "w-1"
        wm._registry.try_get_by_name.return_value = worker  # type: ignore[attr-defined]
        wm._registry.try_pop_by_name = MagicMock()  # type: ignore[attr-defined, method-assign]
        wm._stop_and_destroy_worker = AsyncMock(return_value=False)  # type: ignore[method-assign]

        result = self._run(wm.destroy_worker("w-1"))

        assert result is False
        wm._registry.try_pop_by_name.assert_not_called()
        callback.assert_not_called()

    def test_failed_stop_does_not_release_resources(self) -> None:
        wm = _worker_manager()
        worker = MagicMock()
        worker.name = "w-1"
        worker.status = WorkerStatus.RUNNING
        worker.stop = AsyncMock(return_value=False)
        wm._destroy_worker = MagicMock()  # type: ignore[method-assign]

        result = self._run(wm._stop_and_destroy_worker(worker))

        assert result is False
        wm._destroy_worker.assert_not_called()

    def test_disconnected_worker_requires_provider_stop_confirmation(self) -> None:
        wm = _worker_manager()
        worker = MagicMock()
        worker.name = "w-1"
        worker.status = WorkerStatus.STOPPED
        worker.stop = AsyncMock(return_value=False)
        wm._destroy_worker = MagicMock()  # type: ignore[method-assign]

        result = self._run(wm._stop_and_destroy_worker(worker))

        assert result is False
        worker.stop.assert_awaited_once_with()
        wm._destroy_worker.assert_not_called()

    def test_failed_start_cleanup_keeps_unconfirmed_worker_registered(self) -> None:
        wm = _worker_manager()
        worker = MagicMock()
        worker.status = WorkerStatus.STOPPED
        worker.start = AsyncMock(return_value=False)
        wm._stop_and_destroy_worker = AsyncMock(return_value=False)  # type: ignore[method-assign]
        wm._registry.try_pop = MagicMock()  # type: ignore[attr-defined, method-assign]

        result = self._run(wm._start_worker(worker))

        assert result is False
        wm._registry.try_pop.assert_not_called()


class TestRequestedProviderConfigPolicy:
    def test_request_cannot_choose_worker_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wm = _worker_manager()
        monkeypatch.setattr(env, "FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES", False)

        with pytest.raises(ValueError, match="worker token"):
            wm._validate_requested_worker_config(
                WorkerInitConfig(provider="native", worker_token="known-token")
            )

    @pytest.mark.parametrize(
        "field",
        [
            "container_name",
            "docker_registry",
            "enable_ssh",
            "hf_cache_dir",
            "results_dir",
            "ssh",
            "version",
        ],
    )
    def test_docker_privileged_fields_are_rejected(
        self, field: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wm = _worker_manager()
        monkeypatch.setattr(env, "FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES", False)
        config = WorkerInitConfig(provider="docker", worker_config={field: "value"})

        with pytest.raises(ValueError, match=field):
            wm._validate_requested_worker_config(config)

    def test_docker_allows_resource_selection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wm = _worker_manager()
        monkeypatch.setattr(env, "FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES", False)
        config = WorkerInitConfig(
            provider="docker",
            worker_config={
                "worker_type": "gpu",
                "gpu_count": 1,
                "cuda_devices": [0],
                "worker_alias": "gpu-0",
                "tags": "soc",
            },
        )

        wm._validate_requested_worker_config(config)

    @pytest.mark.parametrize(
        "field",
        [
            "flowmesh_url",
            "hf_cache_dir",
            "openai_api_key",
            "results_dir",
            "supervisor_grpc_target",
        ],
    )
    def test_native_privileged_base_fields_are_rejected(
        self, field: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wm = _worker_manager()
        monkeypatch.setattr(env, "FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES", False)

        with pytest.raises(ValueError, match=field):
            wm._validate_requested_worker_config(
                WorkerInitConfig(provider="native", worker_config={field: "value"})
            )

    @pytest.mark.parametrize(
        "field",
        [
            "docker_registry",
            "flowmesh_url",
            "hf_cache_dir",
            "instance_id",
            "openai_api_key",
            "results_dir",
            "supervisor_grpc_target",
            "vast_api_key",
            "version",
        ],
    )
    def test_vastai_privileged_fields_are_rejected(
        self, field: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wm = _worker_manager()
        monkeypatch.setattr(env, "FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES", False)

        with pytest.raises(ValueError, match=field):
            wm._validate_requested_worker_config(
                WorkerInitConfig(provider="vastai", worker_config={field: "value"})
            )

    @pytest.mark.parametrize("field", ["no_default", "specs"])
    def test_vastai_cannot_relax_offer_trust_requirements(
        self, field: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wm = _worker_manager()
        monkeypatch.setattr(env, "FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES", False)

        with pytest.raises(ValueError, match=field):
            wm._validate_requested_worker_config(
                WorkerInitConfig(provider="vastai", worker_config={field: {}})
            )

    def test_vastai_allows_offer_selection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wm = _worker_manager()
        monkeypatch.setattr(env, "FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES", False)

        wm._validate_requested_worker_config(
            WorkerInitConfig(
                provider="vastai",
                worker_config={
                    "disk": 40,
                    "order": "score-",
                    "search_limit": 5,
                    "worker_alias": "remote-gpu",
                },
            )
        )

    def test_admin_override_switch_allows_privileged_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wm = _worker_manager()
        monkeypatch.setattr(env, "FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES", True)

        wm._validate_requested_worker_config(
            WorkerInitConfig(
                provider="docker",
                worker_token="operator-token",
                worker_config={"results_dir": "/admin/path"},
            )
        )
