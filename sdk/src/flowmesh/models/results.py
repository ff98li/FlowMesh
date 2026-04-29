"""Result-related models."""

from pydantic import BaseModel


class PathResponse(BaseModel):
    ok: bool
    path: str
