from typing import Any, Literal

from ..task_type import TaskType
from .common import ModelInferSpecStrict, ModelInferSpecTemplate

# ── Text-to-Image ────────────────────────────────────────────────────────────


class OmniText2ImageSpecStrict(ModelInferSpecStrict):
    taskType: Literal[TaskType.OMNI_TEXT2IMAGE]
    omni: dict[str, Any] | None = None
    storyboard: dict[str, Any] | None = None


class OmniText2ImageSpecTemplate(ModelInferSpecTemplate):
    taskType: Literal[TaskType.OMNI_TEXT2IMAGE]
    omni: dict[str, Any] | None = None
    storyboard: dict[str, Any] | None = None


# ── Text-to-Speech ───────────────────────────────────────────────────────────


class OmniText2SpeechSpecStrict(ModelInferSpecStrict):
    taskType: Literal[TaskType.OMNI_TEXT2SPEECH]
    omni: dict[str, Any] | None = None
    storyboard: dict[str, Any] | None = None


class OmniText2SpeechSpecTemplate(ModelInferSpecTemplate):
    taskType: Literal[TaskType.OMNI_TEXT2SPEECH]
    omni: dict[str, Any] | None = None
    storyboard: dict[str, Any] | None = None


# ── Text-to-Audio (BGM) ─────────────────────────────────────────────────────


class OmniText2AudioSpecStrict(ModelInferSpecStrict):
    taskType: Literal[TaskType.OMNI_TEXT2AUDIO]
    omni: dict[str, Any] | None = None
    storyboard: dict[str, Any] | None = None


class OmniText2AudioSpecTemplate(ModelInferSpecTemplate):
    taskType: Literal[TaskType.OMNI_TEXT2AUDIO]
    omni: dict[str, Any] | None = None
    storyboard: dict[str, Any] | None = None


# ── Text-to-General (Narration) ──────────────────────────────────────────────


class OmniText2GeneralSpecStrict(ModelInferSpecStrict):
    taskType: Literal[TaskType.OMNI_TEXT2GENERAL]
    omni: dict[str, Any] | None = None
    storyboard: dict[str, Any] | None = None


class OmniText2GeneralSpecTemplate(ModelInferSpecTemplate):
    taskType: Literal[TaskType.OMNI_TEXT2GENERAL]
    omni: dict[str, Any] | None = None
    storyboard: dict[str, Any] | None = None
