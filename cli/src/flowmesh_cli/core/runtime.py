"""CLI runtime helpers built on direct SDK imports."""

from pathlib import Path
from typing import NoReturn

import typer
from flowmesh.client import FlowMesh
from flowmesh.config import DEFAULT_CONFIG_PATH, FlowMeshConfig

from . import logging


def safe_load_config(path: Path = DEFAULT_CONFIG_PATH) -> FlowMeshConfig:
    """Load CLI config with user-friendly error messages."""

    def _error(msg: str) -> NoReturn:
        logging.error(msg)
        raise typer.Exit(code=1)

    try:
        config = FlowMeshConfig.from_file(path)
    except FileNotFoundError:
        _error(
            "Config file not found. "
            "Please run `flowmesh login <url> --api-key <key>`."
        )
    except Exception as exc:
        _error(f"Invalid config file: {exc}. Please re-login.")

    if not config.base_url:
        _error("Missing base_url in config. Please re-login.")
    return config


def flowmesh_client_from_config(config: FlowMeshConfig | None = None) -> FlowMesh:
    """Create an SDK client from the saved CLI config."""
    if config is None:
        config = safe_load_config()
    return FlowMesh(base_url=config.base_url, api_key=config.api_key)
