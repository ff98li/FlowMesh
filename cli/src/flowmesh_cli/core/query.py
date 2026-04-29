"""Utilities for building query parameters for list endpoints."""

from urllib.parse import parse_qsl

import typer

from . import logging


def parse_query_filters(query: list[str] | None) -> list[tuple[str, str]]:
    """Parse repeated --query values into query parameter pairs.

    Accepts either `key=value` or full query strings like `a=1&b=2` (optionally
    prefixed with `?`).
    """
    if not query:
        return []

    pairs: list[tuple[str, str]] = []
    for raw in query:
        chunk = raw.lstrip("?").strip()
        if "=" not in chunk:
            logging.error(f"Invalid query filter: {raw!r}. Use key=value.")
            raise typer.Exit(code=1)
        try:
            parsed = parse_qsl(chunk, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            logging.error(f"Invalid query filter: {raw!r}. Use key=value.")
            raise typer.Exit(code=1)
        for key, value in parsed:
            key = key.strip()
            if not key:
                logging.error(f"Invalid query filter: {raw!r}. Empty key.")
                raise typer.Exit(code=1)
            pairs.append((key, value))
    return pairs
