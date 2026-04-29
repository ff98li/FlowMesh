import logging
from pathlib import Path
from typing import Any

from starlette.requests import HTTPConnection

from .clients import RedisClient
from .dispatcher import Dispatcher
from .registries import NodeRegistry, WorkerRegistry, WorkflowRegistry
from .services.metrics import MetricsRecorder
from .services.monitoring import EventMonitor
from .services.ssh_audit import SshAuditService
from .services.ssh_forward import SshForwardService
from .services.watchdog import WorkerWatchdog
from .task.runtime import TaskRuntime


def get_logger(conn: HTTPConnection) -> logging.Logger:
    return conn.app.state.logger


def get_runtime(conn: HTTPConnection) -> TaskRuntime:
    return conn.app.state.runtime


def get_dispatcher(conn: HTTPConnection) -> Dispatcher:
    return conn.app.state.dispatcher


def get_workflow_registry(conn: HTTPConnection) -> WorkflowRegistry:
    return conn.app.state.workflow_registry


def get_worker_registry(conn: HTTPConnection) -> WorkerRegistry:
    return conn.app.state.worker_registry


def get_node_registry(conn: HTTPConnection) -> NodeRegistry:
    return conn.app.state.node_registry


def get_metrics(conn: HTTPConnection) -> MetricsRecorder:
    return conn.app.state.metrics_recorder


def get_watchdog(conn: HTTPConnection) -> WorkerWatchdog:
    return conn.app.state.watchdog


def get_event_monitor(conn: HTTPConnection) -> EventMonitor:
    return conn.app.state.event_monitor


def get_results_dir(conn: HTTPConnection) -> Path:
    return conn.app.state.results_dir


def get_redis_client(conn: HTTPConnection) -> RedisClient:
    return conn.app.state.redis_client


def get_supervisor(conn: HTTPConnection) -> Any:
    return conn.app.state.supervisor


def get_ssh_forward(conn: HTTPConnection) -> SshForwardService | None:
    return conn.app.state.ssh_forward


def get_ssh_audit(conn: HTTPConnection) -> SshAuditService | None:
    return conn.app.state.ssh_audit


def get_ssh_proxy_enabled(conn: HTTPConnection) -> bool:
    return conn.app.state.ssh_proxy_enabled
