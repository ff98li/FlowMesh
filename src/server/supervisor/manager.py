import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .. import env
from ..hooks import PrincipalContext
from .adapters.base import ProviderSpec, WorkerAdapter, WorkerTokenType
from .adapters.docker import get_provider_spec as docker_provider_spec
from .adapters.native import get_provider_spec as native_provider_spec
from .adapters.vastai import get_provider_spec as vastai_provider_spec
from .registry import WorkerRegistry
from .schemas import WorkerInfo, WorkerStatus

_MAX_PARALLELISM: int = 16
_DOCKER_REQUEST_FIELDS = frozenset(
    {
        "cuda_devices",
        "gpu_count",
        "network_bandwidth",
        "tags",
        "worker_alias",
        "worker_cost_per_hour",
        "worker_type",
    }
)
_NATIVE_REQUEST_FIELDS = _DOCKER_REQUEST_FIELDS
_VASTAI_REQUEST_FIELDS = frozenset(
    {
        "disk",
        "label",
        "network_bandwidth",
        "order",
        "search_limit",
        "tags",
        "worker_alias",
        "worker_cost_per_hour",
    }
)


class WorkerInitConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    provider: str = Field(default="docker", description="Worker provider")
    init_on_start: bool = Field(
        default=True,
        description="Whether to start the worker immediately",
    )
    worker_token: WorkerTokenType | None = Field(
        default=None, description="Optional worker token (overrides registry token)"
    )
    worker_config: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific worker config"
    )

    @property
    def extra_kwargs(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in self.model_dump().items()
            if k not in {"provider", "init_on_start", "worker_token", "worker_config"}
        }


class ServerWorkerConfig(BaseModel):
    default_worker_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Default configuration applied to all workers",
    )
    workers: list[WorkerInitConfig] = Field(
        default_factory=list,
        description="List of worker configurations",
    )


class WorkerManager:
    def __init__(
        self,
        system_principal: PrincipalContext,
        config_path: str,
        registry: WorkerRegistry,
        logger: logging.Logger,
        capacity_change_callback: Callable[[], None] | None = None,
    ) -> None:
        self.config_path = config_path
        self.logger = logger

        self._registry = registry
        self._default_worker_config: dict[str, Any] | None = None
        self._is_started: bool = False
        self._capacity_change_callback = capacity_change_callback
        # Provider specs are built defensively: on hosts without Docker the
        # docker provider constructor raises (docker.from_env is eager), and
        # that must not prevent other providers (e.g. `native`) from loading.
        specs: list[ProviderSpec] = []
        for builder in (
            docker_provider_spec,
            vastai_provider_spec,
            native_provider_spec,
        ):
            try:
                specs.append(builder(system_principal))
            except Exception as exc:
                logger.warning(
                    "Worker provider %s unavailable: %s",
                    getattr(builder, "__name__", builder),
                    exc,
                )
        self._providers: dict[str, ProviderSpec] = {spec.name: spec for spec in specs}

    @property
    def is_started(self) -> bool:
        return self._is_started

    async def start(self) -> None:
        if self.is_started:
            self.logger.warning("WorkerManager is already started.")
            return

        self._is_started = True
        self._default_worker_config = {}

        if not os.path.isfile(self.config_path):
            self.logger.warning(
                (
                    "Worker config file '%s' does not exist. "
                    "Skipping worker initialization."
                ),
                self.config_path,
            )
            return

        # Load worker configs from the config file
        with open(self.config_path, encoding="utf-8") as f:
            raw = f.read()
        config_data = yaml.safe_load(raw) if raw.strip() else None
        if config_data is None:
            self.logger.info(
                "Worker config file '%s' is empty. Skipping worker initialization.",
                self.config_path,
            )
            return

        server_config = ServerWorkerConfig.model_validate(config_data)
        self._default_worker_config = server_config.default_worker_config

        to_start: list[WorkerAdapter] = []
        to_prepare: list[WorkerAdapter] = []
        for init_config in server_config.workers:
            try:
                worker = self._create_worker(init_config)
                worker_info = worker.get_info()
                self.logger.info(
                    "Created worker %s with provider '%s' (status=%s).",
                    worker_info.name,
                    worker_info.provider,
                    worker_info.status,
                )
                if init_config.init_on_start:
                    to_start.append(worker)
                else:
                    to_prepare.append(worker)
            except Exception as exc:
                self.logger.error("Failed to register worker: %s", exc)

        if not (to_start or to_prepare):
            return

        max_parallel = min(len(to_start) + len(to_prepare), _MAX_PARALLELISM)
        sema = asyncio.Semaphore(max_parallel or 1)
        coros: list[Awaitable] = []
        if to_start:

            async def start_worker(worker: WorkerAdapter) -> None:
                async with sema:
                    try:
                        await self._start_worker(worker)
                    except Exception as exc:
                        self.logger.error(
                            "Failed to start worker %s: %s", worker.name, exc
                        )

            coros.extend(start_worker(worker) for worker in to_start)

        if to_prepare:

            async def prepare_worker(worker: WorkerAdapter) -> None:
                async with sema:
                    try:
                        await worker.prepare()
                    except Exception as exc:
                        self.logger.error(
                            "Failed to prepare worker %s: %s", worker.name, exc
                        )

            coros.extend(prepare_worker(worker) for worker in to_prepare)

        await asyncio.gather(*coros)
        self._report_capacity_change()

    async def stop(self) -> None:
        if not self.is_started:
            self.logger.warning("WorkerManager is not started.")
            return

        destroyed = await self._stop_and_destroy_workers(self._registry.all_workers())
        for worker in destroyed:
            self._registry.try_pop(worker.token)
        if destroyed:
            self._report_capacity_change()
        if not self._registry.all_workers():
            for spec in self._providers.values():
                spec.factory.cleanup()
        else:
            self.logger.error(
                "Worker manager stopped with %d worker(s) still running; "
                "their resource reservations remain quarantined only for the "
                "remaining lifetime of this supervisor process (quarantine is "
                "not persisted across a crash or restart).",
                len(self._registry.all_workers()),
            )
        self._default_worker_config = None
        self._is_started = False
        self.logger.info("Worker manager stopped")

    async def create_worker(self, init_config: WorkerInitConfig) -> WorkerInfo:
        if not self.is_started:
            raise RuntimeError("WorkerManager not started")

        self._validate_requested_worker_config(init_config)
        worker = self._create_worker(init_config)
        if init_config.init_on_start:
            started = await self._start_worker(worker)
            if not started:
                raise RuntimeError(f"Failed to start worker '{worker.name}'")
        self._report_capacity_change()
        return worker.get_info()

    def list_workers(self) -> list[WorkerInfo]:
        if not self.is_started:
            return []
        return [worker.get_info() for worker in self._registry.all_workers()]

    def get_worker_info(self, name: str) -> WorkerInfo | None:
        if not self.is_started:
            return None
        worker = self._registry.try_get_by_name(name)
        return None if worker is None else worker.get_info()

    async def start_worker(self, name: str) -> bool:
        if not self.is_started:
            raise RuntimeError("WorkerManager not started")
        worker = self._registry.try_get_by_name(name)
        if worker is None:
            raise ValueError(f"Worker '{name}' does not exist")

        return await self._start_worker(worker)

    async def stop_worker(self, name: str) -> bool:
        if not self.is_started:
            raise RuntimeError("WorkerManager not started")
        worker = self._registry.try_get_by_name(name)
        if worker is None:
            raise ValueError(f"Worker '{name}' does not exist")
        if worker.status not in (WorkerStatus.STARTING, WorkerStatus.RUNNING):
            raise ValueError(f"Worker '{name}' is not starting or running")

        return await self._stop_worker(worker)

    async def destroy_worker(self, name: str) -> bool:
        if not self.is_started:
            raise RuntimeError("WorkerManager not started")
        worker = self._registry.try_get_by_name(name)
        if worker is None:
            return False

        success = await self._stop_and_destroy_worker(worker)
        if success:
            self._registry.try_pop_by_name(name)
            self._report_capacity_change()
        return success

    async def destroy_workers(self, names: set[str] | None = None) -> None:
        if not self.is_started:
            raise RuntimeError("WorkerManager not started")

        workers: list[WorkerAdapter]
        if names is None:
            workers = self._registry.all_workers()
        else:
            missing = [
                name for name in names if not self._registry.exists_by_name(name)
            ]
            if missing:
                raise ValueError(f"Workers not found: {', '.join(missing)}")
            workers = [self._registry.get_by_name(name) for name in names]

        destroyed = await self._stop_and_destroy_workers(workers)
        for worker in destroyed:
            self._registry.try_pop(worker.token)
        if destroyed:
            self._report_capacity_change()
        destroyed_ids = {id(worker) for worker in destroyed}
        failed_names = sorted(
            worker.name for worker in workers if id(worker) not in destroyed_ids
        )
        if failed_names:
            raise RuntimeError(f"Failed to stop worker(s): {', '.join(failed_names)}")

    def _validate_requested_worker_config(self, init_config: WorkerInitConfig) -> None:
        provider = init_config.provider.strip().lower()
        if env.FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES:
            return
        if init_config.worker_token is not None:
            raise ValueError(
                "Request cannot choose a worker token; set "
                "FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES=true to allow it"
            )
        requested_fields = set(init_config.worker_config)
        if provider == "docker":
            forbidden = requested_fields - _DOCKER_REQUEST_FIELDS
        elif provider == "native":
            forbidden = requested_fields - _NATIVE_REQUEST_FIELDS
        elif provider == "vastai":
            forbidden = requested_fields - _VASTAI_REQUEST_FIELDS
        else:
            forbidden = set()
        if forbidden:
            names = ", ".join(sorted(forbidden))
            raise ValueError(
                f"Request cannot set privileged {provider} worker field(s): {names}; "
                "set FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES=true to allow it"
            )

    def _create_worker(self, init_config: WorkerInitConfig) -> WorkerAdapter:
        if not self.is_started:
            raise RuntimeError("WorkerManager not started")

        token = init_config.worker_token or self._registry.new_token()
        provider = init_config.provider.strip().lower()
        worker_config = (self._default_worker_config or {}) | init_config.worker_config

        spec = self._providers.get(provider)
        if spec is None:
            raise ValueError(f"Unsupported worker provider: {provider}")
        config = spec.config_cls.model_validate(worker_config)
        worker = spec.factory.create_worker(token, config)

        try:
            self._registry.add(worker)
        except ValueError:
            self._destroy_worker(worker)
            raise ValueError(f"Worker '{worker.name}' already exists")
        return worker

    async def _start_worker(self, worker: WorkerAdapter) -> bool:
        if not self.is_started:
            raise RuntimeError("WorkerManager not started")
        if worker.status is not WorkerStatus.STOPPED:
            raise ValueError(f"Worker '{worker.name}' is already started")

        started = await worker.start()
        if not started:
            destroyed = await self._stop_and_destroy_worker(worker)
            if destroyed:
                self._registry.try_pop(worker.token)
            return False
        return True

    def _destroy_worker(self, worker: WorkerAdapter) -> None:
        for spec in self._providers.values():
            if isinstance(worker, spec.adapter_cls):
                spec.factory.destroy_worker(worker)
                return
        raise ValueError(f"Unsupported worker type: {type(worker)}")

    def _report_capacity_change(self) -> None:
        callback = self._capacity_change_callback
        if callback is None:
            return
        try:
            callback()
        except Exception as exc:
            self.logger.debug("Failed to report capacity change: %s", exc)

    async def _stop_and_destroy_workers(
        self, workers: list[WorkerAdapter]
    ) -> list[WorkerAdapter]:
        if not workers:
            return []

        max_workers = min(len(workers), _MAX_PARALLELISM)
        sema = asyncio.Semaphore(max_workers or 1)

        async def stop_and_destroy(worker: WorkerAdapter) -> WorkerAdapter | None:
            async with sema:
                success = await self._stop_and_destroy_worker(worker)
                return worker if success else None

        results = await asyncio.gather(
            *(stop_and_destroy(worker) for worker in workers)
        )
        return [worker for worker in results if worker is not None]

    async def _stop_and_destroy_worker(self, worker: WorkerAdapter) -> bool:
        worker_name = worker.name
        success = True

        if worker.status is not WorkerStatus.STOPPING:
            self.logger.info("Stopping worker %s...", worker_name)
            try:
                success = await worker.stop()
            except Exception as exc:
                self.logger.error(
                    "Failed to stop worker %s: %s", worker_name, repr(exc)
                )
                success = False
        else:
            # STOPPING is not proof that the process/container/instance died.
            # In particular, an outer asyncio timeout can cancel the coroutine
            # while its blocking stop operation is still running in a thread.
            success = False

        if not success:
            self.logger.error(
                "Worker %s was not confirmed stopped; keeping it registered and "
                "retaining its resource reservations.",
                worker_name,
            )
            return False

        try:
            self._destroy_worker(worker)
        except Exception as exc:
            self.logger.error("Failed to destroy worker %s: %s", worker_name, repr(exc))
            success = False

        if success:
            self.logger.info("Worker %s stopped.", worker_name)

        return success

    async def _stop_worker(self, worker: WorkerAdapter) -> bool:
        worker_name = worker.name
        if worker.status not in (WorkerStatus.STARTING, WorkerStatus.RUNNING):
            raise ValueError(f"Worker '{worker_name}' is not starting or running")

        self.logger.info("Stopping worker %s...", worker_name)
        try:
            success = await worker.stop()
            if success:
                if self._registry.get_worker_id(worker.token) is None:
                    # Ensure unregistered workers are restartable after stopped.
                    worker.set_status(WorkerStatus.STOPPED)
                self.logger.info("Worker %s stopped.", worker_name)
            else:
                self.logger.error("Failed to stop worker %s", worker_name)
            return success
        except Exception as exc:
            self.logger.error("Failed to stop worker %s: %s", worker_name, repr(exc))
            return False
