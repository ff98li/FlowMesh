import json

import typer
from flowmesh.exceptions import FlowMeshError

from ..core import logging
from ..core.runtime import flowmesh_client_from_config
from ..core.typer import get_typer

app = get_typer(help="Query FlowMesh server system information.")


@app.command()
def metrics() -> None:
    """Retrieve and display system metrics from the FlowMesh server."""
    client = flowmesh_client_from_config()
    try:
        result = client.system.metrics()
    except FlowMeshError as exc:
        logging.error(str(exc))
        raise typer.Exit(code=1)
    logging.log(json.dumps(result, indent=2))
