"""Tests for the FLOWMESH_PLUGINS loader in server.main.

The loader is a top-level snippet in main.py — too coupled to module-init
ordering to import that file in isolation. Instead, this test re-implements
the same expression inline and exercises it on a temporary plugin to confirm:

  - empty / missing env var loads no plugins
  - whitespace and trailing commas are tolerated
  - each named module's install() is invoked
  - import errors propagate (loud failure, not silent skip)
"""

import importlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest


# Mirrors the dispatch in src/server/main.py — kept tiny and verbatim so a
# drift between the test and the real loader is obvious.
def _load_plugins() -> None:
    for _plugin in os.getenv("FLOWMESH_PLUGINS", "").split(","):
        if _plugin := _plugin.strip():
            importlib.import_module(_plugin).install()


@pytest.fixture
def plugin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Create a tmp dir on sys.path holding two minimal plugin packages."""
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    for name in ("alpha_plugin", "beta_plugin", "missing_install_plugin"):
        sys.modules.pop(name, None)


def _write_plugin(root: Path, name: str, body: str) -> None:
    pkg = root / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text(body)


class TestPluginLoader:
    def test_empty_env_loads_nothing(
        self, monkeypatch: pytest.MonkeyPatch, plugin_dir: Path
    ) -> None:
        monkeypatch.delenv("FLOWMESH_PLUGINS", raising=False)
        _load_plugins()  # must not raise

    def test_blank_env_loads_nothing(
        self, monkeypatch: pytest.MonkeyPatch, plugin_dir: Path
    ) -> None:
        monkeypatch.setenv("FLOWMESH_PLUGINS", "")
        _load_plugins()

    def test_single_plugin_installed(
        self, monkeypatch: pytest.MonkeyPatch, plugin_dir: Path
    ) -> None:
        _write_plugin(
            plugin_dir,
            "alpha_plugin",
            "calls = []\ndef install():\n    calls.append('a')\n",
        )
        monkeypatch.setenv("FLOWMESH_PLUGINS", "alpha_plugin")
        _load_plugins()
        assert importlib.import_module("alpha_plugin").calls == ["a"]

    def test_multiple_plugins_in_listed_order(
        self, monkeypatch: pytest.MonkeyPatch, plugin_dir: Path
    ) -> None:
        order: list[str] = []
        body = (
            "import sys\n"
            "def install():\n"
            "    sys.modules['_plugin_loader_order'].append(__name__)\n"
        )
        _write_plugin(plugin_dir, "alpha_plugin", body)
        _write_plugin(plugin_dir, "beta_plugin", body)

        sys.modules["_plugin_loader_order"] = order  # type: ignore[assignment]
        try:
            monkeypatch.setenv("FLOWMESH_PLUGINS", "alpha_plugin , beta_plugin")
            _load_plugins()
        finally:
            del sys.modules["_plugin_loader_order"]

        assert order == ["alpha_plugin", "beta_plugin"]

    def test_trailing_comma_tolerated(
        self, monkeypatch: pytest.MonkeyPatch, plugin_dir: Path
    ) -> None:
        _write_plugin(
            plugin_dir,
            "alpha_plugin",
            "calls = []\ndef install():\n    calls.append('a')\n",
        )
        monkeypatch.setenv("FLOWMESH_PLUGINS", "alpha_plugin,,")
        _load_plugins()
        assert importlib.import_module("alpha_plugin").calls == ["a"]

    def test_missing_module_raises(
        self, monkeypatch: pytest.MonkeyPatch, plugin_dir: Path
    ) -> None:
        monkeypatch.setenv("FLOWMESH_PLUGINS", "no_such_plugin_xyzzy")
        with pytest.raises(ModuleNotFoundError):
            _load_plugins()

    def test_module_without_install_raises(
        self, monkeypatch: pytest.MonkeyPatch, plugin_dir: Path
    ) -> None:
        _write_plugin(plugin_dir, "missing_install_plugin", "pass\n")
        monkeypatch.setenv("FLOWMESH_PLUGINS", "missing_install_plugin")
        with pytest.raises(AttributeError):
            _load_plugins()
