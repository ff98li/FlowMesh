"""CLI command behavior tests using CliRunner with mocked SDK client."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import typer
from flowmesh.models import (
    WorkflowSubmitResponse,
)
from flowmesh_cli.cli import build_cli_app
from typer.testing import CliRunner

runner = CliRunner()


def _app() -> typer.Typer:
    return build_cli_app()


def _mock_client(**resource_overrides: MagicMock) -> MagicMock:
    """Build a mock FlowMesh client with resource namespaces."""
    client = MagicMock()
    for attr in (
        "workflows",
        "tasks",
        "results",
        "workers",
        "servers",
        "system",
    ):
        if attr not in resource_overrides:
            setattr(client, attr, MagicMock())
    for attr, mock in resource_overrides.items():
        setattr(client, attr, mock)
    return client


# ------------------------------------------------------------------ #
# Workflow commands
# ------------------------------------------------------------------ #


class TestWorkflowSubmit:
    def test_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(
            _app(), ["workflow", "submit", str(tmp_path / "missing.yaml")]
        )
        assert result.exit_code != 0
        assert "not found" in result.stdout.lower() or result.exit_code == 1

    @patch("flowmesh_cli.commands.workflow.flowmesh_client_from_config")
    def test_format_flag(self, mock_hc: MagicMock, tmp_path: Path) -> None:
        tmpl = tmp_path / "wf.json"
        tmpl.write_text('{"nodes": []}')
        client = _mock_client()
        client.workflows.submit.return_value = WorkflowSubmitResponse(
            ok=True, workflow_id="wf-1", count=1, tasks=[]
        )
        mock_hc.return_value = client

        result = runner.invoke(
            _app(), ["workflow", "submit", str(tmpl), "--format", "n8n"]
        )
        assert result.exit_code == 0
        client.workflows.submit.assert_called_once()
        call_args = client.workflows.submit.call_args
        assert call_args.args[0] == '{"nodes": []}'
        assert call_args.kwargs["workflow_format"] == "n8n"


class TestWorkflowList:
    @patch("flowmesh_cli.commands.workflow.flowmesh_client_from_config")
    def test_status_filter(self, mock_hc: MagicMock) -> None:
        client = _mock_client()
        client.workflows.list.return_value = []
        mock_hc.return_value = client

        result = runner.invoke(_app(), ["workflow", "list", "--status", "DONE"])
        assert result.exit_code == 0
        client.workflows.list.assert_called_once()
        call_kwargs = client.workflows.list.call_args.kwargs
        assert call_kwargs["status"] == ["DONE"]

    @patch("flowmesh_cli.commands.workflow.flowmesh_client_from_config")
    def test_query_filter_forwarded(self, mock_hc: MagicMock) -> None:
        client = _mock_client()
        client.workflows.list.return_value = []
        mock_hc.return_value = client

        result = runner.invoke(
            _app(),
            ["workflow", "list", "--query", "owner_id=u-1", "--query", "status=DONE"],
        )
        assert result.exit_code == 0
        call_kwargs = client.workflows.list.call_args.kwargs
        assert call_kwargs["query_params"] == [
            ("owner_id", "u-1"),
            ("status", "DONE"),
        ]


# ------------------------------------------------------------------ #
# Task commands
# ------------------------------------------------------------------ #


class TestTaskInfo:
    @patch("flowmesh_cli.commands.task.flowmesh_client_from_config")
    def test_id_forwarded(self, mock_hc: MagicMock) -> None:
        client = _mock_client()
        task_mock = MagicMock()
        task_mock.model_dump_json.return_value = '{"task_id": "t-123"}'
        client.tasks.retrieve.return_value = task_mock
        mock_hc.return_value = client

        result = runner.invoke(_app(), ["task", "info", "t-123"])
        assert result.exit_code == 0
        client.tasks.retrieve.assert_called_once_with("t-123")


# ------------------------------------------------------------------ #
# Logout
# ------------------------------------------------------------------ #


class TestLogout:
    def test_logout_removes_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('base_url = "http://localhost:8000"')
        assert config_path.exists()

        result = runner.invoke(_app(), ["logout", "--config", str(config_path)])
        assert result.exit_code == 0
        assert not config_path.exists()
