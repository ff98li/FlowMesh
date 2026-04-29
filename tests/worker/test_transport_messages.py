"""Tests for gRPC/protobuf message serialization boundaries."""

from shared.schemas.command import (
    InterruptMessage,
    StopMessage,
    TaskMessage,
)


class TestMessageSerialization:
    def test_task_message_json_roundtrip(self) -> None:
        msg = TaskMessage(
            worker_id="w-1",
            payload={
                "task_id": "t-abc",
                "workflow_id": "wf-123",
                "owner_id": "usr-1",
                "assigned_worker": "w-1",
                "dispatched_at": "2025-01-15T10:00:00Z",
                "task": {
                    "apiVersion": "flowmesh/v1",
                    "kind": "Task",
                    "spec": {"taskType": "echo", "data": {"items": ["hello"]}},
                },
            },
        )
        json_str = msg.model_dump_json()
        restored = TaskMessage.model_validate_json(json_str)
        assert restored.worker_id == "w-1"
        assert restored.payload["task_id"] == "t-abc"
        assert restored.kind == "task"

    def test_interrupt_message_json(self) -> None:
        msg = InterruptMessage(task_id="t-1", worker_id="w-1", reason="cancelled")
        json_str = msg.model_dump_json()
        restored = InterruptMessage.model_validate_json(json_str)
        assert restored.task_id == "t-1"
        assert restored.kind == "interrupt"

    def test_stop_message_json(self) -> None:
        msg = StopMessage(task_id="t-1", worker_id="w-1", reason="stopped")
        json_str = msg.model_dump_json()
        restored = StopMessage.model_validate_json(json_str)
        assert restored.task_id == "t-1"
        assert restored.kind == "stop"

    def test_dispatch_messages_distinguishable(self) -> None:
        """All dispatch message types have distinct `kind` discriminators."""
        task = TaskMessage(worker_id="w-1", payload={})
        interrupt = InterruptMessage(task_id="t-1", worker_id="w-1")
        stop = StopMessage(task_id="t-1", worker_id="w-1")

        kinds = {task.kind, interrupt.kind, stop.kind}
        assert kinds == {"task", "interrupt", "stop"}

    def test_large_payload_serializable(self) -> None:
        """Payloads with nested structures should serialize cleanly."""
        payload = {
            "task_id": "t-1",
            "task": {
                "spec": {
                    "taskType": "inference",
                    "model": {"source": {"identifier": "meta-llama/Llama-3.1-8B"}},
                    "data": {
                        "messages": [
                            {"role": "system", "content": "You are helpful."},
                            {"role": "user", "content": "Hello " * 1000},
                        ]
                    },
                }
            },
        }
        msg = TaskMessage(worker_id="w-1", payload=payload)
        json_str = msg.model_dump_json()
        assert len(json_str) > 5000
        restored = TaskMessage.model_validate_json(json_str)
        assert restored.payload["task_id"] == "t-1"
