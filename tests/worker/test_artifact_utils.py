"""Tests for `worker.executors.utils.artifacts`.

Pure-logic helpers (no pandas/datasets/PIL) — runnable in CI without
the worker-side extras.
"""

from pathlib import Path

import pytest

from worker.executors.base_executor import ExecutionError
from worker.executors.utils.artifacts import (
    artifact_to_source,
    maybe_resolve_artifact_ref,
)


class TestArtifactToSource:
    def test_unwrapped_upstream_yields_url(self, tmp_path: Path) -> None:
        upstream = {
            "_artifacts": {
                "base_url": "http://host:8010",
                "base_dir": (tmp_path / "producer-tid").as_posix(),
            },
            "result": {"images": [{"path": "a.png"}]},
        }
        url = artifact_to_source({"path": "a.png"}, {"producer": upstream}, "producer")
        assert url == "http://host:8010/api/v1/results/producer-tid/files/a.png"

    def test_envelope_wrapped_upstream_yields_url(self, tmp_path: Path) -> None:
        """Server stores results.json as `{task_id, ..., result: {...}}`; the
        helper must unwrap one level to find `_artifacts`."""
        upstream = {
            "task_id": "producer-tid",
            "result": {
                "_artifacts": {
                    "base_url": "http://host:8010",
                    "base_dir": (tmp_path / "producer-tid").as_posix(),
                },
            },
        }
        url = artifact_to_source({"path": "x.png"}, {"producer": upstream}, "producer")
        assert url == "http://host:8010/api/v1/results/producer-tid/files/x.png"

    def test_local_file_takes_fast_path(self, tmp_path: Path) -> None:
        task_root = tmp_path / "producer-tid"
        (task_root / "artifacts").mkdir(parents=True)
        (task_root / "artifacts" / "a.png").write_bytes(b"\x89PNG")
        upstream = {
            "_artifacts": {
                "base_url": "http://host:8010",
                "base_dir": task_root.as_posix(),
            }
        }
        resolved = artifact_to_source(
            {"path": "a.png"}, {"producer": upstream}, "producer"
        )
        assert resolved == (task_root / "artifacts" / "a.png").as_posix()

    def test_local_only_upstream_returns_local_path(self, tmp_path: Path) -> None:
        task_root = tmp_path / "producer-tid"
        upstream = {"_artifacts": {"base_url": None, "base_dir": task_root.as_posix()}}
        resolved = artifact_to_source(
            {"path": "a.png"}, {"producer": upstream}, "producer"
        )
        assert resolved == (task_root / "artifacts" / "a.png").as_posix()

    def test_missing_context_raises(self) -> None:
        with pytest.raises(ExecutionError, match="_artifacts context is missing"):
            artifact_to_source({"path": "a.png"}, {"producer": {}}, "producer")

    def test_missing_path_raises(self) -> None:
        with pytest.raises(ExecutionError, match="non-empty 'path' field"):
            artifact_to_source({}, {"producer": {}}, "producer")


class TestMaybeResolveArtifactRef:
    def test_passes_through_non_dict(self) -> None:
        assert maybe_resolve_artifact_ref("hello", None, None) == "hello"
        assert maybe_resolve_artifact_ref(42, None, None) == 42
        assert maybe_resolve_artifact_ref([1, 2], None, None) == [1, 2]

    def test_passes_through_dict_without_path(self) -> None:
        value = {"url": "http://x"}
        assert maybe_resolve_artifact_ref(value, None, None) is value

    def test_resolves_path_dict(self, tmp_path: Path) -> None:
        upstream = {
            "_artifacts": {
                "base_url": "http://host:8010",
                "base_dir": (tmp_path / "producer-tid").as_posix(),
            }
        }
        out = maybe_resolve_artifact_ref(
            {"path": "a.png"}, {"producer": upstream}, "producer"
        )
        assert out == "http://host:8010/api/v1/results/producer-tid/files/a.png"
