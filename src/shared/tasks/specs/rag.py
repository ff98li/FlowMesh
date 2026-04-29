from typing import Any, Literal

from ..task_type import TaskType
from .common import TaskSpecStrictBase, TaskSpecTemplateBase


class RagSpecStrict(TaskSpecStrictBase):
    taskType: Literal[TaskType.RAG]

    qdrant: dict[str, Any] | None = None
    embedding: dict[str, Any] | None = None
    search: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    query: str | None = None


class RagSpecTemplate(TaskSpecTemplateBase):
    taskType: Literal[TaskType.RAG]

    qdrant: dict[str, Any] | None = None
    embedding: dict[str, Any] | None = None
    search: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    query: str | None = None
