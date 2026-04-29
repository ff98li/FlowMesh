"""Filesystem path helpers shared by FlowMesh tooling."""

from pathlib import Path


def resolve_path(value: str, default: str, base_dir: Path) -> Path:
    """Resolve a possibly relative path against a base directory."""
    raw = value.strip() or default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (base_dir / path).resolve()


def ensure_dir(path: Path) -> None:
    """Create a directory if it does not exist."""
    path.mkdir(parents=True, exist_ok=True)


def ensure_file(path: Path) -> None:
    """Create a file and its parent directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
