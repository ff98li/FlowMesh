import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from server import env
from server.routers.health import router
from shared.schemas.command import CommandResponse
from shared.schemas.worker import WorkerStatus


def _app() -> FastAPI:
    app = FastAPI()
    control = MagicMock()
    control.ping = AsyncMock(return_value=True)
    telemetry = MagicMock()
    telemetry.ping = AsyncMock(return_value=True)
    app.state.redis_client = SimpleNamespace(
        asyncio=SimpleNamespace(
            control_client=control,
            telemetry_client=telemetry,
        )
    )
    app.state.node_registry = SimpleNamespace(
        list_nodes_async=AsyncMock(return_value=[])
    )
    supervisor = MagicMock()
    supervisor.is_alive.return_value = True
    supervisor.exec_cmd = AsyncMock(
        return_value=CommandResponse(command_id="cmd", success=True, data={})
    )
    app.state.supervisor = supervisor
    app.state.worker_registry = SimpleNamespace(
        list_workers_async=AsyncMock(
            return_value=[SimpleNamespace(stale=False, status=WorkerStatus.IDLE)]
        )
    )
    app.state.logger = logging.getLogger("test.health")
    app.include_router(router)
    return app


@pytest.mark.anyio
async def test_livez_does_not_probe_dependencies() -> None:
    app = _app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    app.state.redis_client.asyncio.control_client.ping.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/readyz", "/healthz"])
async def test_readiness_checks_dependencies_and_workers(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(env, "FLOWMESH_READY_MIN_WORKERS", 1)
    async with AsyncClient(
        transport=ASGITransport(app=_app()), base_url="http://test"
    ) as client:
        response = await client.get(path)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert all(payload["checks"].values())
    assert payload["details"]["workers"] == "healthy=1, required=1"


@pytest.mark.anyio
async def test_readiness_failure_is_503_and_does_not_expose_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app()
    app.state.redis_client.asyncio.control_client.ping.side_effect = RuntimeError(
        "redis://admin:secret@example.invalid"
    )
    monkeypatch.setattr(env, "FLOWMESH_READY_MIN_WORKERS", 1)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["ok"] is False
    assert response.json()["checks"]["redis_control"] is False
    assert "secret" not in response.text


@pytest.mark.anyio
async def test_worker_node_requires_fresh_local_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app()
    app.state.worker_registry = None
    app.state.supervisor.exec_cmd.return_value = CommandResponse(
        command_id="cmd",
        success=True,
        data={
            "workers": [
                {
                    "status": "RUNNING",
                    "heartbeat_fresh": False,
                }
            ]
        },
    )
    monkeypatch.setattr(env, "FLOWMESH_READY_MIN_WORKERS", 1)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"]["workers"] is False
