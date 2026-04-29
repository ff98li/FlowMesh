"""Tests for filter_models_by_queries — the generic query filter."""

import pytest
from pydantic import BaseModel

from server.utils.misc import filter_models_by_queries


class _SampleModel(BaseModel):
    id: str
    status: str
    stale: bool = False
    tags: list[str] = []
    env: dict = {}
    score: float | None = None


def _make(id: str, status: str = "IDLE", **kw) -> _SampleModel:
    return _SampleModel(id=id, status=status, **kw)


# ---------- Fixtures ----------

_MODELS = [
    _make("w-1", tags=["gpu", "a100"], env={"region": "us-east"}, score=1.0),
    _make("w-2", status="BUSY", tags=["cpu"], stale=True, score=2.0),
    _make("w-3", tags=["gpu"], env={"region": "eu-west"}, score=3.0),
    _make("w-4", status="STOPPED", score=None),
]


# ---------- Tests ----------


@pytest.mark.parametrize(
    "query, expected_ids",
    [
        # Exact match
        ({"status": "IDLE"}, {"w-1", "w-3"}),
        ({"status": "BUSY"}, {"w-2"}),
        # No matches
        ({"status": "UNKNOWN"}, set()),
        # Empty query returns all
        ({}, {"w-1", "w-2", "w-3", "w-4"}),
        # Unknown key ignored
        ({"nonexistent": "val"}, {"w-1", "w-2", "w-3", "w-4"}),
    ],
    ids=["exact", "exact-busy", "no-match", "empty-query", "unknown-key"],
)
def test_basic_filtering(query: dict, expected_ids: set[str]) -> None:
    result = filter_models_by_queries(_MODELS, query)
    assert {m.id for m in result} == expected_ids


def test_repeated_key_or_semantics() -> None:
    """?status=IDLE&status=BUSY should match either."""

    class _MultiItems:
        def multi_items(self):
            return [("status", "IDLE"), ("status", "BUSY")]

    result = filter_models_by_queries(_MODELS, _MultiItems())  # type: ignore[arg-type]
    assert {m.id for m in result} == {"w-1", "w-2", "w-3"}


def test_nested_dot_notation() -> None:
    """Dot-notation matches nested dict fields; models where traversal
    fails (empty env) are NOT excluded — the unknown key is skipped."""
    result = filter_models_by_queries(_MODELS, {"env.region": "us-east"})
    # w-1 matches, w-3 has eu-west (excluded), w-2 and w-4 have no
    # env.region so the key is skipped (they pass through).
    assert "w-1" in {m.id for m in result}
    assert "w-3" not in {m.id for m in result}


def test_list_membership() -> None:
    result = filter_models_by_queries(_MODELS, {"tags": "gpu"})
    assert {m.id for m in result} == {"w-1", "w-3"}


@pytest.mark.parametrize(
    "query_value",
    ["true", "True", "1", "yes", "on"],
    ids=lambda v: f"truthy-{v}",
)
def test_boolean_truthy(query_value: str) -> None:
    result = filter_models_by_queries(_MODELS, {"stale": query_value})
    assert {m.id for m in result} == {"w-2"}


@pytest.mark.parametrize(
    "query_value",
    ["false", "False", "0", "no", "off"],
    ids=lambda v: f"falsy-{v}",
)
def test_boolean_falsy(query_value: str) -> None:
    result = filter_models_by_queries(_MODELS, {"stale": query_value})
    assert {m.id for m in result} == {"w-1", "w-3", "w-4"}


@pytest.mark.parametrize(
    "query_value",
    ["null", "None", ""],
    ids=lambda v: f"null-{v!r}",
)
def test_none_matching(query_value: str) -> None:
    result = filter_models_by_queries(_MODELS, {"score": query_value})
    assert {m.id for m in result} == {"w-4"}


def test_csv_tag_string() -> None:
    """If tags are stored as comma-separated string, membership still works."""

    class _CsvModel(BaseModel):
        id: str
        tags: str

    models = [_CsvModel(id="a", tags="gpu,a100"), _CsvModel(id="b", tags="cpu")]
    result = filter_models_by_queries(models, {"tags": "gpu"})
    assert [m.id for m in result] == ["a"]
