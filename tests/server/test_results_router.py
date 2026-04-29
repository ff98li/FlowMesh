from pathlib import Path
from typing import cast

import pytest
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute

from server.routers.v1 import results as results_router


def test_download_result_file_route_uses_path_converter() -> None:
    route = next(
        route
        for route in results_router.router.routes
        if isinstance(route, APIRoute)
        and route.path == "/results/{task_id}/files/{filename:path}"
    )
    route = cast(APIRoute, route)
    assert route.path == "/results/{task_id}/files/{filename:path}"


@pytest.mark.anyio
async def test_download_result_file_resolves_flat_name_under_artifacts(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task-1"
    artifacts_dir = task_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    artifact_path = artifacts_dir / "result.json"
    artifact_path.write_text('{"ok":true}', encoding="utf-8")

    response = await results_router.download_result_file(
        task_id="task-1",
        filename="result.json",
        results_dir=tmp_path,
    )

    assert isinstance(response, FileResponse)
    assert Path(response.path) == artifact_path


@pytest.mark.anyio
async def test_download_result_file_falls_back_to_task_root_for_flat_filename(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task-1"
    task_dir.mkdir(parents=True)
    root_file = task_dir / "result.json"
    root_file.write_text('{"ok":true}', encoding="utf-8")

    response = await results_router.download_result_file(
        task_id="task-1",
        filename="result.json",
        results_dir=tmp_path,
    )

    assert isinstance(response, FileResponse)
    assert Path(response.path) == root_file


def test_resolve_artifact_relative_path_scopes_nested_paths_to_artifacts() -> None:
    assert results_router._resolve_artifact_path("result.json") == Path(
        "artifacts/result.json"
    )
    assert results_router._resolve_artifact_path("nested/result.json") == Path(
        "artifacts/nested/result.json"
    )
    assert results_router._resolve_artifact_path("artifacts/result.json") == Path(
        "artifacts/artifacts/result.json"
    )
    assert results_router._resolve_artifact_path(
        "artifacts/nested/result.json"
    ) == Path("artifacts/artifacts/nested/result.json")


def test_resolve_artifact_relative_path_rejects_invalid_paths() -> None:
    with pytest.raises(Exception):
        results_router._resolve_artifact_path("../result.json")
