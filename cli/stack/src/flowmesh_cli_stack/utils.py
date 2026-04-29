import os
from pathlib import Path

from flowmesh import FlowMesh
from flowmesh_cli.core.assets import asset_path
from flowmesh_stack.env import load_env
from flowmesh_stack.node_client import NodeClient
from flowmesh_stack.paths import ensure_dir, ensure_file, resolve_path

DEFAULT_ENV_FILE = Path(".env")
STACK_PATH_KEYS = {
    "REDIS_TLS_DIR",
    "SERVER_TLS_DIR",
    "SERVER_WORKER_CONFIG",
}


def stack_compose_file() -> Path:
    return asset_path("flowmesh_cli_stack.assets", "compose.yml")


def stack_env_example() -> Path:
    return asset_path("flowmesh_cli_stack.assets", ".env.example")


def stack_bake_file() -> Path:
    return asset_path("flowmesh_cli_stack.assets", "docker-bake.hcl")


def stack_node_client(
    env_file: Path, base_url: str | None, token: str | None
) -> NodeClient:
    load_env(env_file, base_dir=Path.cwd(), path_keys=STACK_PATH_KEYS)
    default_base = "http://{}:{}".format(
        os.getenv("SERVER_HOST", "localhost"),
        os.getenv("SERVER_HTTP_PORT", os.getenv("SERVER_APP_PORT", "8000")),
    )
    resolved_base = base_url or default_base
    resolved_token = token or os.getenv("SERVER_TOKEN") or None
    return NodeClient(resolved_base, token=resolved_token)


def flowmesh_client(
    env_file: Path, base_url: str | None, api_key: str | None
) -> FlowMesh:
    load_env(env_file, base_dir=Path.cwd(), path_keys=STACK_PATH_KEYS)
    return FlowMesh(base_url=base_url, api_key=api_key)


def ensure_deploy_paths(base_dir: Path) -> None:
    ensure_dir(
        resolve_path(
            os.getenv("REDIS_TLS_DIR", ""),
            default="./secrets/tls/redis",
            base_dir=base_dir,
        )
    )
    ensure_dir(
        resolve_path(
            os.getenv("SERVER_TLS_DIR", ""),
            default="./secrets/tls/server",
            base_dir=base_dir,
        )
    )
    ensure_file(
        resolve_path(
            os.getenv("SERVER_WORKER_CONFIG", ""),
            default="./configs/worker_config.yaml",
            base_dir=base_dir,
        )
    )
