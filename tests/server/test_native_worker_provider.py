from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from server import env
from server.hooks import PrincipalContext
from server.supervisor.adapters.base import WorkerTokenType
from server.supervisor.adapters.native import (
    NativeWorkerAdapter,
    NativeWorkerConfig,
    WorkerType,
)
from server.supervisor.resource_manager import GpuArch


def _owner() -> PrincipalContext:
    return PrincipalContext(
        principal_id="test-admin",
        org_id="test-org",
        external_id="test-admin",
        principal_type="admin",
        scopes=["*"],
    )


def _adapter(
    *,
    token: str = "worker-token",
    name: str = "native-worker",
    config: NativeWorkerConfig | None = None,
    devices: list[int] | None = None,
    device_tokens: list[str] | None = None,
) -> NativeWorkerAdapter:
    config = config or NativeWorkerConfig()
    return NativeWorkerAdapter(
        token=WorkerTokenType(token),
        name=name,
        cuda_devices=devices,
        cuda_device_tokens=device_tokens,
        gpu_arch=GpuArch.UNKNOWN if devices else None,
        config=config,
        owner=_owner(),
    )


@pytest.mark.parametrize("field", ["command", "cwd", "log_dir", "hb_file"])
def test_native_config_rejects_process_and_path_overrides(field: str) -> None:
    value: object = ["sh"] if field == "command" else "/untrusted"
    with pytest.raises(ValidationError):
        NativeWorkerConfig.model_validate({field: value})


def test_native_log_path_cannot_escape_admin_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(env, "WORKER_HB_DIR", tmp_path.as_posix())
    worker = _adapter(token="../../escape", name="../../escape")

    log_path = Path(worker._log_path()).resolve()

    assert log_path.is_relative_to((tmp_path / "native" / "logs").resolve())
    assert "escape" not in log_path.name

    heartbeat_path = Path(worker._environment()["WORKER_HB_FILE"]).resolve()
    assert heartbeat_path.is_relative_to((tmp_path / "native").resolve())
    assert "escape" not in heartbeat_path.name


def test_native_log_path_rejects_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_root = tmp_path / "runtime-root"
    outside = tmp_path / "outside"
    (configured_root / "native").mkdir(parents=True)
    outside.mkdir()
    (configured_root / "native" / "logs").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(env, "WORKER_HB_DIR", configured_root.as_posix())

    with pytest.raises(RuntimeError, match="escapes"):
        _adapter()._log_path()


def test_native_start_uses_fixed_worker_entrypoint_and_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(env, "WORKER_HB_DIR", tmp_path.as_posix())
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    monkeypatch.setenv("CUDA_HOME", "/opt/cuda")
    monkeypatch.setenv("STACK_PGADMIN_PASSWORD", "must-not-leak")
    worker = _adapter()
    proc = MagicMock()
    proc.poll.return_value = None
    worker._probe_hardware = MagicMock(return_value=None)  # type: ignore[method-assign]

    with (
        patch(
            "server.supervisor.adapters.native.subprocess.Popen", return_value=proc
        ) as popen,
        patch("server.supervisor.adapters.native.time.sleep"),
    ):
        assert worker._start() is True

    args, kwargs = popen.call_args
    assert args[0][-2:] == ["-m", "worker.main"]
    assert kwargs["cwd"] == worker._worker_cwd()
    assert kwargs["env"]["PATH"] == "/usr/local/bin:/usr/bin"
    assert kwargs["env"]["CUDA_HOME"] == "/opt/cuda"
    assert "STACK_PGADMIN_PASSWORD" not in kwargs["env"]


def test_native_process_environment_does_not_inherit_unrelated_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(env, "WORKER_HB_DIR", tmp_path.as_posix())
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    monkeypatch.setenv("CUDA_HOME", "/opt/cuda")
    monkeypatch.setenv("SLURM_JOB_ID", "12345")
    monkeypatch.setenv("STACK_PGADMIN_PASSWORD", "must-not-leak")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "must-not-leak")

    process_env = _adapter()._process_environment()

    assert process_env["PATH"] == "/usr/local/bin:/usr/bin"
    assert process_env["CUDA_HOME"] == "/opt/cuda"
    assert process_env["SLURM_JOB_ID"] == "12345"
    assert "STACK_PGADMIN_PASSWORD" not in process_env
    assert "MINIO_ROOT_PASSWORD" not in process_env


def test_native_gpu_environment_preserves_parent_allocation_tokens() -> None:
    worker = _adapter(
        config=NativeWorkerConfig(worker_type=WorkerType.GPU),
        devices=[0, 1],
        device_tokens=["GPU-first", "MIG-GPU-parent/1/0"],
    )

    environment = worker._environment()

    assert environment["CUDA_VISIBLE_DEVICES"] == "GPU-first,MIG-GPU-parent/1/0"
    assert environment["WORKER_HOST_GPU_ID"] == "GPU-first,MIG-GPU-parent/1/0"
    assert environment["FLOWMESH_VISIBLE_GPU_TOKENS"] == (
        '["GPU-first", "MIG-GPU-parent/1/0"]'
    )
