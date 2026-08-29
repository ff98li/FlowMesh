import asyncio
from typing import Any

from fastapi import APIRouter, Request, Response, status

from shared.schemas.command import CommandMessage, CommandType
from shared.schemas.worker import WorkerStatus

from .. import env
from ..schemas.common import OkResponse, ReadinessResponse

router = APIRouter(tags=["Health", "Caller: anyone"])


@router.get(
    "/livez",
    name="livez",
    summary="Liveness check",
    description="Reports whether the HTTP process can serve requests.",
    response_description="Liveness status",
)
async def livez() -> OkResponse:
    return OkResponse(ok=True)


async def _bounded(awaitable: Any) -> bool:
    try:
        result = await asyncio.wait_for(awaitable, timeout=2.0)
        return result is not False
    except Exception:
        return False


async def _supervisor_readiness(
    supervisor: Any,
) -> tuple[bool, list[dict[str, Any]]]:
    if supervisor is None:
        return True, []
    if not supervisor.is_alive():
        return False, []
    try:
        response = await supervisor.exec_cmd(
            CommandMessage(command=CommandType.GET_WORKERS), timeout=2.0
        )
    except Exception:
        return False, []
    return response.success, (response.data or {}).get("workers", [])


async def _registered_worker_count(worker_registry: Any) -> tuple[bool, int | None]:
    if worker_registry is None:
        return True, None
    try:
        workers = await asyncio.wait_for(
            worker_registry.list_workers_async(), timeout=2.0
        )
    except Exception:
        return False, 0
    count = sum(
        not worker.stale and worker.status in (WorkerStatus.IDLE, WorkerStatus.BUSY)
        for worker in workers
    )
    return True, count


async def _readiness(request: Request) -> ReadinessResponse:
    checks: dict[str, bool] = {}
    details: dict[str, str] = {}

    redis_client = request.app.state.redis_client
    node_registry = request.app.state.node_registry
    supervisor = request.app.state.supervisor
    worker_registry = request.app.state.worker_registry
    (
        checks["redis_control"],
        checks["redis_telemetry"],
        checks["registry"],
        supervisor_result,
        worker_result,
    ) = await asyncio.gather(
        _bounded(redis_client.asyncio.control_client.ping()),
        _bounded(redis_client.asyncio.telemetry_client.ping()),
        _bounded(node_registry.list_nodes_async()),
        _supervisor_readiness(supervisor),
        _registered_worker_count(worker_registry),
    )

    checks["supervisor"], local_workers = supervisor_result
    if supervisor is None:
        details["supervisor"] = "disabled by configuration"

    worker_registry_ready, registered_worker_count = worker_result
    checks["registry"] = checks["registry"] and worker_registry_ready
    if registered_worker_count is None:
        healthy_worker_count = sum(
            worker.get("status") == "RUNNING" and worker.get("heartbeat_fresh") is True
            for worker in local_workers
        )
    else:
        healthy_worker_count = registered_worker_count

    minimum_workers = env.FLOWMESH_READY_MIN_WORKERS
    checks["workers"] = healthy_worker_count >= minimum_workers
    details["workers"] = f"healthy={healthy_worker_count}, required={minimum_workers}"
    return ReadinessResponse(ok=all(checks.values()), checks=checks, details=details)


@router.get(
    "/readyz",
    name="readyz",
    summary="Readiness check",
    description="Checks Redis, registries, supervisor control, and worker freshness.",
    response_description="Readiness status",
)
@router.get(
    "/healthz",
    name="healthz",
    summary="Readiness check (compatibility alias)",
    description="Compatibility alias for /readyz.",
    response_description="Readiness status",
)
async def readyz(request: Request, response: Response) -> ReadinessResponse:
    readiness = await _readiness(request)
    if not readiness.ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness
