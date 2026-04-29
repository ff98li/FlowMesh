from fastapi import APIRouter, Depends, HTTPException, Request, status

from ...app_state import (
    get_worker_registry,
)
from ...registries.worker import WorkerInfo, WorkerRegistry
from ...utils.misc import filter_models_by_queries

router = APIRouter(prefix="/workers", tags=["Workers"])


@router.get(
    "",
    summary="List workers",
    description="List all registered workers with optional filtering.",
    response_description="List of workers",
)
async def list_workers(
    request: Request,
    registry: WorkerRegistry = Depends(get_worker_registry),
) -> list[WorkerInfo]:
    queries = request.query_params
    workers = await registry.list_workers_async()
    return filter_models_by_queries(workers, queries)


@router.get(
    "/{worker_id}",
    summary="Get a worker",
    description="Get worker information by ID.",
    response_description="Worker information",
)
async def get_worker(
    worker_id: str,
    registry: WorkerRegistry = Depends(get_worker_registry),
) -> WorkerInfo:
    worker = await registry.get_worker_async(worker_id)
    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="worker not found"
        )
    stale = await registry.is_worker_stale_async(worker.id)
    return WorkerInfo(**worker.model_dump(), stale=stale)
