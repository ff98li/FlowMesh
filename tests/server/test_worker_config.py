"""Tests for server worker configuration models."""

from server.supervisor.manager import ServerWorkerConfig, WorkerInitConfig


class TestWorkerInitConfig:
    def test_defaults(self) -> None:
        cfg = WorkerInitConfig()
        assert cfg.provider == "docker"
        assert cfg.init_on_start is True
        assert cfg.worker_config == {}

    def test_custom_provider(self) -> None:
        cfg = WorkerInitConfig(provider="vastai", init_on_start=False)
        assert cfg.provider == "vastai"
        assert cfg.init_on_start is False

    def test_extra_fields_preserved(self) -> None:
        cfg = WorkerInitConfig(  # type: ignore[call-arg]
            provider="docker",
            worker_config={"image": "my-image:latest"},
            custom_field="custom_value",
        )
        extras = cfg.extra_kwargs
        assert "custom_field" in extras
        assert extras["custom_field"] == "custom_value"
        assert "provider" not in extras
        assert "worker_config" not in extras

    def test_worker_config_nested(self) -> None:
        cfg = WorkerInitConfig(
            worker_config={
                "image": "flowmesh_worker:gpu",
                "gpu_count": 4,
                "env": {"CUDA_VISIBLE_DEVICES": "0,1,2,3"},
            }
        )
        assert cfg.worker_config["gpu_count"] == 4


class TestServerWorkerConfig:
    def test_defaults(self) -> None:
        cfg = ServerWorkerConfig()
        assert cfg.default_worker_config == {}
        assert cfg.workers == []

    def test_with_workers(self) -> None:
        cfg = ServerWorkerConfig(
            default_worker_config={"tags": "gpu"},
            workers=[
                WorkerInitConfig(provider="docker"),
                WorkerInitConfig(provider="vastai", init_on_start=False),
            ],
        )
        assert len(cfg.workers) == 2
        assert cfg.workers[0].provider == "docker"
        assert cfg.workers[1].provider == "vastai"
