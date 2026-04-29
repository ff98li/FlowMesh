"""Verify tracked .env.example files match schema-generated output."""

import argparse
import difflib
from pathlib import Path

from flowmesh_cli_stack.env_schema import STACK_ENV_SCHEMA
from flowmesh_stack.env_schema import render_env_example


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="Overwrite example files with generated content.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    checks = [
        (
            STACK_ENV_SCHEMA,
            repo_root
            / "cli"
            / "stack"
            / "src"
            / "flowmesh_cli_stack"
            / "assets"
            / ".env.example",
        ),
    ]

    mismatches: list[str] = []
    for schema, example_path in checks:
        rendered = render_env_example(schema)
        if args.write:
            example_path.write_text(rendered)
            print(f"Wrote {example_path}")
            continue
        current = example_path.read_text() if example_path.exists() else ""
        if current != rendered:
            mismatches.append(str(example_path))
            diff = difflib.unified_diff(
                current.splitlines(),
                rendered.splitlines(),
                fromfile=str(example_path),
                tofile=f"{example_path} (generated)",
                lineterm="",
            )
            print("\n".join(diff))

    if mismatches and not args.write:
        print("\nMismatched env example files:")
        for path in mismatches:
            print(f"- {path}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
