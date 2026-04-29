import uuid

from .adapters.base import WorkerAdapter, WorkerTokenType


class WorkerRegistry:
    def __init__(self) -> None:
        self._registry: dict[WorkerTokenType, WorkerAdapter] = {}
        self._name_token_map: dict[str, WorkerTokenType] = {}
        self._token_id_map: dict[WorkerTokenType, str] = {}

    def new_token(self) -> WorkerTokenType:
        return uuid.uuid4().hex  # type: ignore

    def add(self, worker: WorkerAdapter) -> None:
        token = worker.token
        name = worker.name
        if token in self._registry:
            raise ValueError(f"Worker with token '{token}' already exists")
        if name in self._name_token_map:
            raise ValueError(f"Worker with name '{name}' already exists")
        self._registry[token] = worker
        self._name_token_map[name] = token

    def exists(self, token: WorkerTokenType) -> bool:
        return token in self._registry

    def get(self, token: WorkerTokenType) -> WorkerAdapter:
        return self._registry[token]

    def try_get(self, token: WorkerTokenType) -> WorkerAdapter | None:
        return self._registry.get(token)

    def pop(self, token: WorkerTokenType) -> WorkerAdapter:
        worker = self._registry.pop(token)
        del self._name_token_map[worker.name]
        self._token_id_map.pop(token, None)
        return worker

    def try_pop(self, token: WorkerTokenType) -> WorkerAdapter | None:
        worker = self._registry.pop(token, None)
        if worker is None:
            return None
        del self._name_token_map[worker.name]
        self._token_id_map.pop(token, None)
        return worker

    def clear(self) -> None:
        self._registry.clear()
        self._name_token_map.clear()
        self._token_id_map.clear()

    def exists_by_name(self, name: str) -> bool:
        return name in self._name_token_map

    def get_by_name(self, name: str) -> WorkerAdapter:
        token = self._name_token_map[name]
        return self._registry[token]

    def try_get_by_name(self, name: str) -> WorkerAdapter | None:
        token = self._name_token_map.get(name)
        if token is None:
            return None
        return self._registry.get(token)

    def pop_by_name(self, name: str) -> WorkerAdapter:
        token = self._name_token_map.pop(name)
        worker = self._registry.pop(token)
        self._token_id_map.pop(token, None)
        return worker

    def try_pop_by_name(self, name: str) -> WorkerAdapter | None:
        token = self._name_token_map.pop(name, None)
        if token is None:
            return None
        self._token_id_map.pop(token, None)
        return self._registry.pop(token)

    def all_workers(self) -> list[WorkerAdapter]:
        return list(self._registry.values())

    def set_worker_id(self, token: WorkerTokenType, worker_id: str) -> None:
        self._token_id_map[token] = worker_id

    def get_worker_id(self, token: WorkerTokenType) -> str | None:
        return self._token_id_map.get(token)
