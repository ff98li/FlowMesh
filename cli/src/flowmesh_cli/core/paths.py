from pathlib import Path

import typer

from . import logging


def resolve_path(value: str, default: str, base_dir: Path) -> Path:
    raw = value.strip() or default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (base_dir / path).resolve()


def ensure_dir(path: Path) -> None:
    if not path.exists():
        logging.warning(f"Directory '{path}' does not exist. Creating it.")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logging.error(f"Failed to create directory '{path}': {exc}")
        raise typer.Exit(code=1) from exc


def ensure_file(path: Path) -> None:
    if not path.exists():
        logging.warning(f"File '{path}' does not exist. Creating it.")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
    except OSError as exc:
        logging.error(f"Failed to create file '{path}': {exc}")
        raise typer.Exit(code=1) from exc
