"""CLI construction tests."""

from flowmesh_cli.cli import build_cli_app
from typer.testing import CliRunner


def test_cli_app_can_be_constructed() -> None:
    app = build_cli_app()

    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "workflow" in result.stdout
    assert "stack" in result.stdout
