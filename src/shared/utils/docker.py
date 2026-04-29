import re


def sanitize_container_name(value: str, maxlen: int | None = None) -> str | None:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value)
    sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-_.")
    sanitized = re.sub(r"^[^A-Za-z0-9]+", "", sanitized)
    if maxlen is not None and len(sanitized) > maxlen:
        sanitized = sanitized[:maxlen].rstrip("-_.")
    return sanitized or None
