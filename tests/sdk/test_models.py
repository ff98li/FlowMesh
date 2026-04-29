"""Model validation and round-trip tests for SDK Pydantic models."""

import pytest
from flowmesh.models import (
    LogQueryResponse,
    Node,
    NodeWorkerInfo,
    OkResponse,
    TaskInfo,
    TaskUsage,
    WorkerHardware,
    WorkerInfo,
    Workflow,
    WorkflowSubmitResponse,
    WorkflowValidateResponse,
)
from flowmesh.models.ssh import SSHConnectionInfo
from pydantic import BaseModel

from server.registries.node import Node as SrvNode
from server.registries.worker import Worker as SrvWorker
from server.registries.worker import WorkerInfo as SrvWorkerInfo
from server.registries.workflow import Workflow as SrvWorkflow
from server.registries.workflow import WorkflowStatus as SrvWorkflowStatus
from server.schemas.common import OkResponse as SrvOkResponse
from server.schemas.logs import LogEntry as SrvLogEntry
from server.schemas.logs import LogEvent as SrvLogEvent
from server.schemas.logs import LogQueryResponse as SrvLogQueryResponse
from server.schemas.node import CPUInfo as SrvCPUInfo
from server.schemas.node import GpuInfo as SrvGpuInfo
from server.schemas.node import GpuPlatformInfo as SrvGpuPlatformInfo
from server.schemas.node import HostInfo as SrvHostInfo
from server.schemas.node import MemoryInfo as SrvMemoryInfo
from server.schemas.node import NetworkInfo as SrvNetworkInfo
from server.schemas.node import NodeWorkerInfo as SrvNodeWorkerInfo
from server.schemas.node import NodeWorkerStatus as SrvNodeWorkerStatus
from server.schemas.node import StorageInfo as SrvStorageInfo
from server.schemas.node import WorkerHardware as SrvWorkerHardware
from server.schemas.ssh import SSHConnectionInfo as SrvSSHConnectionInfo
from server.schemas.workflow import WorkflowSubmitResponse as SrvWorkflowSubmitResponse
from server.schemas.workflow import (
    WorkflowSubmitTaskEntry as SrvWorkflowSubmitTaskEntry,
)
from server.schemas.workflow import (
    WorkflowValidateResponse as SrvWorkflowValidateResponse,
)
from server.schemas.workflow import (
    WorkflowValidateTaskEntry as SrvWorkflowValidateTaskEntry,
)
from server.task.models import TaskInfo as SrvTaskInfo
from server.task.models import TaskUsage as SrvTaskUsage
from shared.schemas.worker import WorkerStatus as SharedWorkerStatus
from shared.tasks.envelope import TaskEnvelopeTemplate
from shared.tasks.specs.misc import EchoSpecTemplate
from shared.tasks.task_type import TaskType as SharedTaskType
from shared.tasks.worker_message import CPUInfo as SharedCPUInfo
from shared.tasks.worker_message import GpuInfo as SharedGpuInfo
from shared.tasks.worker_message import GpuPlatformInfo as SharedGpuPlatformInfo
from shared.tasks.worker_message import HardwareUsage as SharedHardwareUsage
from shared.tasks.worker_message import MemoryInfo as SharedMemoryInfo
from shared.tasks.worker_message import NetworkInfo as SharedNetworkInfo
from shared.tasks.worker_message import WorkerHardware as SharedWorkerHardware

# ------------------------------------------------------------------ #
# Server-side model instances — single source of truth for test payloads
# ------------------------------------------------------------------ #

_SRV_HARDWARE = SrvWorkerHardware(
    cpu=SrvCPUInfo(logical_cores=16, model="AMD EPYC", arch="x86_64"),
    memory=SrvMemoryInfo(total_bytes=68719476736),
    gpu=SrvGpuPlatformInfo(
        gpus=[
            SrvGpuInfo(
                index=0, name="A100", memory_total_bytes=85899345920, uuid="GPU-0"
            )
        ],
    ),
    network=SrvNetworkInfo(ip="10.0.0.1"),
    storage=SrvStorageInfo(disk_space=500.0),
    host=SrvHostInfo(os_version="Ubuntu 22.04"),
)

_SRV_WORKFLOW = SrvWorkflow(
    workflow_id="wf-abc123",
    task_ids=["t-1", "t-2"],
    submitted_at="2025-01-15T10:30:00Z",
    updated_at="2025-01-15T10:31:00Z",
    status=SrvWorkflowStatus.DONE,
    dispatched_tasks=["t-1", "t-2"],
    completed_tasks=["t-1", "t-2"],
    failed_tasks=[],
    cancelled_tasks=[],
)

_SRV_TASK_USAGE = SrvTaskUsage(
    started_at="2025-01-15T10:30:00Z",
    finished_at="2025-01-15T10:31:00Z",
    runtime_sec=60.0,
    hardware=SharedHardwareUsage(
        gpu=SharedGpuPlatformInfo(driver_version=None, cuda_version=None, gpus=[])
    ),
    cost_per_hour=2.5,
    total_cost=0.042,
    status="DONE",
)

_ECHO_SPEC = EchoSpecTemplate(taskType=SharedTaskType.ECHO)
_TASK_ENVELOPE = TaskEnvelopeTemplate(
    apiVersion="flowmesh/v1", kind="Task", spec=_ECHO_SPEC
)

_SRV_TASK_INFO = SrvTaskInfo(
    task_id="t-abc",
    workflow_id="wf-abc",
    owner_id="usr-1",
    raw_yaml="apiVersion: flowmesh/v1\nkind: Task",
    task=_TASK_ENVELOPE,
    status="DONE",
    task_type="echo",
    submitted_at="2025-01-15T10:30:00Z",
    submitted_ts=1705312200.0,
    usages=[_SRV_TASK_USAGE],
    attempts=1,
    max_attempts=3,
    load=1,
    depends_on=[],
    pending_dependencies=[],
    dependents=["t-def"],
    completed=True,
    failed=False,
)

_SHARED_HARDWARE = SharedWorkerHardware(
    cpu=SharedCPUInfo(logical_cores=16, model="AMD EPYC"),
    memory=SharedMemoryInfo(total_bytes=68719476736),
    gpu=SharedGpuPlatformInfo(
        driver_version=None,
        cuda_version=None,
        gpus=[
            SharedGpuInfo(
                index=0, name="A100", uuid="GPU-0", memory_total_bytes=85899345920
            )
        ],
    ),
    network=SharedNetworkInfo(ip="10.0.0.1", bandwidth_bytes_per_sec=None),
)

_SRV_WORKER = SrvWorker(
    id="w-1",
    alias="gpu-a100-01",
    namespace="default",
    cluster="us-west",
    node_id="g-1",
    node_alias="node-01",
    status=SharedWorkerStatus.IDLE,
    hardware=_SHARED_HARDWARE,
    tags=["gpu", "a100"],
)

_SRV_WORKER_INFO = SrvWorkerInfo(
    **_SRV_WORKER.model_dump(),
    stale=False,
)

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _dump(server_obj: BaseModel) -> dict:
    """Dump a server Pydantic model to a JSON-compatible dict."""
    return server_obj.model_dump(mode="json")


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #


class TestWorkflowModels:
    def test_workflow_validate(self) -> None:
        wf = Workflow.model_validate(_dump(_SRV_WORKFLOW))
        assert wf.workflow_id == "wf-abc123"
        assert wf.status == "DONE"

    def test_workflow_submit_response(self) -> None:
        server = SrvWorkflowSubmitResponse(
            ok=True,
            workflow_id="wf-1",
            count=2,
            tasks=[
                SrvWorkflowSubmitTaskEntry(task_id="t-1", status="PENDING"),
                SrvWorkflowSubmitTaskEntry(task_id="t-2", depends_on=["t-1"]),
            ],
        )
        resp = WorkflowSubmitResponse.model_validate(_dump(server))
        assert resp.ok is True
        assert resp.count == 2

    def test_workflow_validate_response(self) -> None:
        server = SrvWorkflowValidateResponse(
            ok=True,
            count=1,
            tasks=[
                SrvWorkflowValidateTaskEntry(
                    task_id="t-mock", graph_node_name="step1", depends_on=[]
                )
            ],
        )
        resp = WorkflowValidateResponse.model_validate(_dump(server))
        assert resp.ok is True


class TestTaskModels:
    def test_task_info_validate(self) -> None:
        task = TaskInfo.model_validate(_dump(_SRV_TASK_INFO))
        assert task.task_id == "t-abc"
        assert task.completed is True

    def test_task_usage(self) -> None:
        usage = TaskUsage.model_validate(_dump(_SRV_TASK_USAGE))
        assert usage.runtime_sec == 60.0
        assert usage.total_cost == pytest.approx(0.042)


class TestWorkerModels:
    def test_worker_info_validate(self) -> None:
        w = WorkerInfo.model_validate(_dump(_SRV_WORKER_INFO))
        assert w.id == "w-1"
        assert w.status == "IDLE"
        assert w.hardware is not None
        assert w.hardware.cpu is not None
        assert w.hardware.cpu.logical_cores == 16

    def test_worker_info_accepts_string_tags(self) -> None:
        payload = _dump(_SRV_WORKER_INFO)
        payload["tags"] = "gpu,a100"
        w = WorkerInfo.model_validate(payload)
        assert w.tags == ["gpu", "a100"]

    def test_worker_hardware_roundtrip(self) -> None:
        hw = WorkerHardware.model_validate(_dump(_SRV_HARDWARE))
        dumped = hw.model_dump(mode="json")
        hw2 = WorkerHardware.model_validate(dumped)
        assert hw2.cpu is not None and hw.cpu is not None
        assert hw2.cpu.logical_cores == hw.cpu.logical_cores


class TestNodeModels:
    def test_node_validate(self) -> None:
        node = SrvNode(
            id="g-1",
            namespace="default",
            cluster="us-west",
            alias="node-01",
            tags=["gpu"],
        )
        payload = {k: getattr(node, k) for k in SrvNode.model_fields}
        g = Node.model_validate(payload)
        assert g.id == "g-1"

    def test_node_worker_info(self) -> None:
        node = SrvNodeWorkerInfo(
            id="w-1",
            name="worker-a100",
            namespace="default",
            cluster="us-west",
            node_id="g-1",
            node_alias="node-01",
            provider="docker",
            status=SrvNodeWorkerStatus.IDLE,
        )
        w = NodeWorkerInfo.model_validate(_dump(node))
        assert w.name == "worker-a100"
        assert w.node_id == "g-1"


class TestMiscModels:
    def test_ok_response(self) -> None:
        server = SrvOkResponse(ok=True)
        r = OkResponse.model_validate(_dump(server))
        assert r.ok is True

    def test_log_query_response(self) -> None:
        server = SrvLogQueryResponse(
            entries=[
                SrvLogEntry(
                    cursor="1705312200000-0",
                    event=SrvLogEvent(
                        ts="2025-01-15T10:30:00Z",
                        message="Starting task",
                        level="INFO",
                    ),
                )
            ],
            next_cursor="1705312200001-0",
        )
        r = LogQueryResponse.model_validate(_dump(server))
        assert len(r.entries) == 1
        assert r.entries[0].event.message == "Starting task"

    def test_ssh_connection_info(self) -> None:
        server = SrvSSHConnectionInfo(
            connection_id="conn-1",
            access_mode="proxy",
            task_id="t-1",
            connected_at="2025-01-15T10:30:00Z",
        )
        r = SSHConnectionInfo.model_validate(_dump(server))
        assert r.access_mode == "proxy"
