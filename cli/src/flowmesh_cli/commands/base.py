from pathlib import Path

import typer
from flowmesh.config import DEFAULT_CONFIG_PATH
from flowmesh.exceptions import FlowMeshError

from ..core import logging
from ..core.runtime import flowmesh_client_from_config
from ..core.typer import get_typer

app = get_typer()


@app.command()
def logout(
    config_path: Path = typer.Option(
        DEFAULT_CONFIG_PATH, "--config", help="Path to configuration file to remove"
    )
) -> None:
    """Delete saved server credentials and configuration."""
    config_path.unlink(missing_ok=True)
    logging.success(f"Logout successful. Removed config {config_path}")


@app.command()
def info() -> None:
    """Query server health status and basic system information."""
    client = flowmesh_client_from_config()
    try:
        resp = client.system.health()
    except FlowMeshError as exc:
        logging.error(str(exc))
        raise typer.Exit(code=1)
    logging.log(resp.model_dump_json(indent=2))


@app.command()
def health() -> None:
    """Check if the FlowMesh server is reachable and healthy."""
    info()
