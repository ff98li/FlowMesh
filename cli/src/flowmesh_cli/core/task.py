"""Task status utilities for the FlowMesh CLI."""

import typer
from flowmesh.exceptions import FlowMeshError
from flowmesh.models.common import TaskStatus

from . import logging
from .runtime import flowmesh_client_from_config


def wait_for_task_completion(task_id: str, interval: float) -> tuple[str, str | None]:
    """Poll task until it reaches a terminal state."""
    client = flowmesh_client_from_config()
    try:
        task = client.tasks.wait(task_id, interval=interval)
        status = task.status
        match status:
            case TaskStatus.DONE:
                return TaskStatus.DONE, None
            case TaskStatus.FAILED | TaskStatus.CANCELLED:
                error = task.error or status.lower()
                return status, error
            case _:
                return status, task.error
    except KeyboardInterrupt:
        logging.warning("Cancelled by user.")
        raise typer.Exit(code=1)
    except FlowMeshError as exc:
        logging.error(str(exc))
        raise typer.Exit(code=1)
