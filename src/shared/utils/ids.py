"""Prefixed identifier factories for FlowMesh objects.

Each FlowMesh object kind gets a short, dashed prefix so that IDs are
self-describing in logs, API responses, and CLI output.
"""

import secrets
import uuid

PREFIX_WORKFLOW = "wfl"
PREFIX_TASK = "tsk"
PREFIX_WORKER = "wkr"
PREFIX_NODE = "nde"
PREFIX_SSH_CONNECTION = "scn"
PREFIX_SSH_SESSION = "ssn"
PREFIX_SUPERVISOR_COMMAND = "cmd"


def _uuid_str() -> str:
    return str(uuid.uuid4())


def _uuid_hex() -> str:
    return uuid.uuid4().hex


def new_workflow_id() -> str:
    return f"{PREFIX_WORKFLOW}-{_uuid_str()}"


def new_task_id() -> str:
    return f"{PREFIX_TASK}-{_uuid_str()}"


def new_worker_id(seq: int) -> str:
    return f"{PREFIX_WORKER}-{seq}"


def new_node_id(seq: int) -> str:
    return f"{PREFIX_NODE}-{seq}"


def new_ssh_connection_id() -> str:
    return f"{PREFIX_SSH_CONNECTION}-{secrets.token_hex(16)}"


def new_ssh_session_id() -> str:
    return f"{PREFIX_SSH_SESSION}-{_uuid_hex()}"


def new_supervisor_command_id() -> str:
    return f"{PREFIX_SUPERVISOR_COMMAND}-{_uuid_hex()}"


__all__ = [
    "PREFIX_NODE",
    "PREFIX_SSH_CONNECTION",
    "PREFIX_SSH_SESSION",
    "PREFIX_SUPERVISOR_COMMAND",
    "PREFIX_TASK",
    "PREFIX_WORKER",
    "PREFIX_WORKFLOW",
    "new_node_id",
    "new_ssh_connection_id",
    "new_ssh_session_id",
    "new_supervisor_command_id",
    "new_task_id",
    "new_worker_id",
    "new_workflow_id",
]
