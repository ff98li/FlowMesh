import importlib
from collections.abc import Sequence

from agents import Tool

from .config import AgentConfig, EnvConfig
from .utils import get_logger, load_class_from_file

logger = get_logger(__name__)


class BaseEnv:
    def __init__(self, config: EnvConfig, trace_id: str | None = None):
        self.config = config
        self.trace_id = trace_id

    async def __aenter__(self) -> "BaseEnv":
        await self.build()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup()

    async def build(self) -> None:
        return None

    async def cleanup(self) -> None:
        return None

    async def get_tools(self) -> list[Tool]:
        return []

    def get_state(self) -> str | None:
        return None


class DummyEnv(BaseEnv):
    pass


ENV_MAP: dict[str, type[BaseEnv]] = {
    "base": BaseEnv,
    "dummy": DummyEnv,
}


def _load_env_class_from_path(class_path: str) -> type[BaseEnv]:
    if ":" in class_path:
        module_path, class_name = class_path.split(":", 1)
    else:
        module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    env_class = getattr(module, class_name)
    return env_class


def _resolve_env_class(env_config: EnvConfig) -> type[BaseEnv]:
    env_name = env_config.name or "dummy"
    if env_name in ENV_MAP:
        return ENV_MAP[env_name]

    config = env_config.config or {}
    filepath = config.get("customized_filepath") or config.get("filepath")
    classname = config.get("customized_classname") or config.get("classname")
    if filepath and classname:
        return load_class_from_file(filepath, classname)

    class_path = config.get("class_path") or config.get("class")
    if class_path:
        return _load_env_class_from_path(class_path)

    if "." in env_name or ":" in env_name:
        return _load_env_class_from_path(env_name)

    raise ValueError(f"Unknown env: {env_name}")


async def get_env(config: AgentConfig, trace_id: str | None = None) -> BaseEnv:
    env_config = config.env
    env_class = _resolve_env_class(env_config)
    if not issubclass(env_class, BaseEnv):
        raise TypeError(f"Env class {env_class} must inherit from BaseEnv to be used.")
    env = env_class(env_config, trace_id=trace_id)
    logger.info(f"Initialized env {env_class.__name__} with config {env_config}")
    return env


__all__: Sequence[str] = ["BaseEnv", "DummyEnv", "get_env"]
