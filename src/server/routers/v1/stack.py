"""Local stack worker management"""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from shared.schemas.command import CommandMessage, CommandType

from ...app_state import get_supervisor
from ...supervisor.supervisor import WorkerSupervisor

router = APIRouter(prefix="/stack/workers", tags=["Stack"])

_WORKER_CREATE_TIMEOUT = 600.0


async def _exec(
    supervisor: WorkerSupervisor,
    cmd: CommandMessage,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Send a command to the local supervisor and return the response data."""
    try:
        kwargs = {"timeout": timeout} if timeout is not None else {}
        resp = await supervisor.exec_cmd(cmd, **kwargs)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)
        )
    if not resp.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=resp.message or "Command failed",
        )
    return resp.data or {}


@router.get("")
async def list_workers(
    supervisor: WorkerSupervisor = Depends(get_supervisor),
) -> list[dict[str, Any]]:
    cmd = CommandMessage(command=CommandType.GET_WORKERS)
    data = await _exec(supervisor, cmd)
    return data.get("workers", [])


@router.post("")
async def create_worker(
    request: Request, supervisor: WorkerSupervisor = Depends(get_supervisor)
) -> dict[str, Any]:
    body = await request.json()
    cmd = CommandMessage(command=CommandType.CREATE_WORKER, payload=body)
    return await _exec(supervisor, cmd, timeout=_WORKER_CREATE_TIMEOUT)


@router.get("/{name}")
async def get_worker(
    name: str, supervisor: WorkerSupervisor = Depends(get_supervisor)
) -> dict[str, Any]:
    cmd = CommandMessage(command=CommandType.GET_WORKERS)
    data = await _exec(supervisor, cmd)
    workers: list[dict[str, Any]] = data.get("workers", [])
    for w in workers:
        if w.get("name") == name:
            return w
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found"
    )


@router.post("/{name}/start")
async def start_worker(
    name: str, supervisor: WorkerSupervisor = Depends(get_supervisor)
) -> None:
    cmd = CommandMessage(
        command=CommandType.START_WORKER, payload={"worker_name": name}
    )
    data = await _exec(supervisor, cmd)
    if not data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start worker '{name}'",
        )


@router.post("/{name}/stop")
async def stop_worker(
    name: str, supervisor: WorkerSupervisor = Depends(get_supervisor)
) -> None:
    cmd = CommandMessage(command=CommandType.STOP_WORKER, payload={"worker_name": name})
    data = await _exec(supervisor, cmd)
    if not data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop worker '{name}'",
        )


@router.delete("/{name}")
async def destroy_worker(
    name: str, supervisor: WorkerSupervisor = Depends(get_supervisor)
) -> None:
    cmd = CommandMessage(
        command=CommandType.DESTROY_WORKER, payload={"worker_name": name}
    )
    await _exec(supervisor, cmd)


@router.delete("")
async def destroy_all_workers(
    request: Request, supervisor: WorkerSupervisor = Depends(get_supervisor)
) -> None:
    body = await request.body()
    names: list[str] | None = None
    if body.strip():
        try:
            raw = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON payload: {exc.msg}",
            )
        if raw is None:
            names = None
        elif isinstance(raw, list):
            names = [str(n) for n in raw]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Expected request body to be an array of worker names.",
            )

    payload = None if names is None else {"worker_names": names}
    cmd = CommandMessage(command=CommandType.DESTROY_WORKERS, payload=payload)
    await _exec(supervisor, cmd)
