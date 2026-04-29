from typing import Literal

from ..task_type import TaskType
from .common import ModelInferSpecStrict, ModelInferSpecTemplate


class DiffusionSpecStrict(ModelInferSpecStrict):
    taskType: Literal[TaskType.DIFFUSION]


class DiffusionSpecTemplate(ModelInferSpecTemplate):
    taskType: Literal[TaskType.DIFFUSION]
