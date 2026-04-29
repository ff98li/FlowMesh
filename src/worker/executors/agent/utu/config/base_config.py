from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

ReprArgs = Iterable[tuple[str | None, Any]]

SECURE_FIELDS = ("api_key", "base_url")


def if_need_secure(key: str) -> bool:
    return any(f in key.lower() for f in SECURE_FIELDS)


def secure_repr(obj: ReprArgs) -> ReprArgs:
    for k, v in obj:
        if k is not None and if_need_secure(k):
            yield k, "***"
        else:
            yield k, v


class ConfigBaseModel(BaseModel):
    """Base model for config, with secure repr"""

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        params = ", ".join(f"{k}={v!r}" for k, v in secure_repr(self.__repr_args__()))
        return f"{self.__class__.__name__}({params})"
