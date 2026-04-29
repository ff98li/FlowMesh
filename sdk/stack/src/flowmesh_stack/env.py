"""Environment file helpers shared by FlowMesh tooling."""

import os
from pathlib import Path
from urllib.parse import urlparse


def parse_env_file(env_file: Path) -> dict[str, str]:
    """Parse a .env file into key/value pairs."""
    values: dict[str, str] = {}
    if not env_file.exists():
        return values
    for line in env_file.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        stripped = stripped.removeprefix("export ").strip()
        key, value = stripped.split("=", 1)
        values[key.strip()] = _normalize_env_value(value)
    return values


def parse_bool(value: str) -> bool | None:
    """Parse a string into a boolean value."""
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return None


def parse_int(value: str) -> int | None:
    """Parse a string into an integer value."""
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def parse_float(value: str) -> float | None:
    """Parse a string into a float value."""
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def is_url(value: str, schemes: set[str] | None = None) -> bool:
    """Check if a string is a valid URL with optional scheme restrictions."""
    parsed = urlparse(value.strip())
    if not (parsed.scheme and parsed.netloc):
        return False
    if schemes and parsed.scheme not in schemes:
        return False
    return True


def validate_env_file(
    env_file: Path,
    example: Path | None = None,
    expected_keys: set[str] | None = None,
) -> tuple[dict[str, str] | None, list[str]]:
    """Validate an env file against an example template or key set."""
    errors: list[str] = []
    if not env_file.exists():
        return None, [f"env file not found: {env_file}"]
    if expected_keys is None:
        if example is None or not example.exists():
            return parse_env_file(env_file), errors
        expected_keys = _parse_env_keys(example)

    actual_keys = _parse_env_keys(env_file)
    missing = sorted(expected_keys - actual_keys)
    unexpected = sorted(actual_keys - expected_keys)
    if missing:
        errors.append(f"Missing required env vars in {env_file}: {', '.join(missing)}")
    if unexpected:
        errors.append(f"Unexpected env vars in {env_file}: {', '.join(unexpected)}")
    return parse_env_file(env_file), errors


def ensure_env_file(env_file: Path, example: Path) -> bool:
    """Create an env file from an example if it does not exist."""
    if env_file.exists() or not example.exists():
        return False
    env_file.write_text(example.read_text())
    return True


def load_env(
    env_file: Path,
    base_dir: Path | None = None,
    path_keys: set[str] | None = None,
) -> None:
    """Load env vars from a file into ``os.environ``."""
    env_key = (env_file, base_dir, path_keys)
    if getattr(load_env, "_loaded", None) == env_key:
        return
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if path_keys and key in path_keys and value:
            expanded = Path(value).expanduser()
            if expanded.is_absolute():
                os.environ[key] = str(expanded)
            elif base_dir is not None:
                os.environ[key] = str((base_dir / expanded).resolve())
            else:
                os.environ[key] = value
        else:
            os.environ[key] = value
    load_env._loaded = env_key  # type: ignore[attr-defined]


def _parse_env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.exists():
        return keys
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        stripped = stripped.removeprefix("export ").strip()
        key = stripped.split("=", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


def _normalize_env_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        stripped = stripped[1:-1]
    return stripped.strip()
