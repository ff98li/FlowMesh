from pydantic import BaseModel, Field


class SSHConnectionInfo(BaseModel):
    connection_id: str = Field(description="Server-tracked SSH connection identifier.")
    access_mode: str = Field(description="SSH access mode.")
    task_id: str = Field(description="Task identifier.")
    workflow_id: str | None = Field(default=None, description="Workflow identifier.")
    worker_id: str | None = Field(
        default=None, description="Assigned worker identifier."
    )
    node_id: str | None = Field(default=None, description="Node identifier.")
    session_id: str | None = Field(default=None, description="SSH session identifier.")
    username: str | None = Field(default=None, description="SSH username.")
    source_ip: str | None = Field(
        default=None, description="Observed client source IP address."
    )
    source_port: int | None = Field(
        default=None, description="Observed client source TCP port."
    )
    connected_at: str = Field(description="Connection start timestamp.")
