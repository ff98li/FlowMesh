"""FlowMesh Docker image reference management.

Provides the canonical mapping from build targets to image references,
used by both the CLI dev commands and programmatic build/deploy scripts.
"""

BUILD_TARGETS: dict[str, str] = {
    "flowmesh_server": "{registry}/flowmesh_server:{version}",
    "flowmesh_worker_cpu": "{registry}/flowmesh_worker:{version}-cpu",
    "flowmesh_worker_gpu_builder": "{registry}/flowmesh_worker_builder:{version}-gpu",
    "flowmesh_worker_gpu": "{registry}/flowmesh_worker:{version}-gpu",
    "flowmesh_ssh_cpu": "{registry}/flowmesh_ssh:{version}-cpu",
    "flowmesh_ssh_gpu": "{registry}/flowmesh_ssh:{version}-gpu",
}
"""Mapping from build target name to image reference format string."""

BUILD_GROUPS: dict[str, list[str]] = {
    "server": ["flowmesh_server"],
    "workers": [
        "flowmesh_worker_cpu",
        "flowmesh_worker_gpu",
        "flowmesh_ssh_cpu",
        "flowmesh_ssh_gpu",
    ],
    "builders": ["flowmesh_worker_gpu_builder"],
}
"""Mapping from group name to list of build targets."""
BUILD_GROUPS["default"] = [
    target for group in ("server", "workers") for target in BUILD_GROUPS[group]
]


def get_image_ref(registry: str, version: str, target: str) -> str:
    """Resolve a Docker image reference for a build target.

    Args:
        registry: Container registry (e.g. ``ghcr.io/mlsys-io``).
        version: Image version tag (e.g. ``dev``, ``0.1.0``).
        target: Build target name (must be a key in :data:`BUILD_TARGETS`).

    Raises:
        ValueError: If the target is unknown.
    """
    if target not in BUILD_TARGETS:
        raise ValueError(f"Unknown build target: {target}")
    return BUILD_TARGETS[target].format(registry=registry, version=version)
