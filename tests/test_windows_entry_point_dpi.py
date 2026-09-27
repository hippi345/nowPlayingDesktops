from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _first_statements(path: Path) -> list[ast.stmt]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return list(tree.body)


def _calls_set_process_dpi_aware_before_import(module_path: Path, imported_module: str) -> None:
    statements = _first_statements(module_path)
    dpi_index: int | None = None
    import_index: int | None = None
    for index, statement in enumerate(statements):
        if isinstance(statement, ast.If) and dpi_index is None:
            for node in ast.walk(statement):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "set_process_dpi_aware"
                ):
                    dpi_index = index
                    break
        if isinstance(statement, ast.ImportFrom) and statement.module == imported_module:
            import_index = index
            break
    assert dpi_index is not None, f"{module_path} never calls set_process_dpi_aware"
    assert import_index is not None, f"{module_path} never imports {imported_module}"
    assert dpi_index < import_index, (
        f"{module_path} must call set_process_dpi_aware before importing {imported_module}"
    )


def test_main_module_calls_dpi_before_cli_import():
    _calls_set_process_dpi_aware_before_import(
        REPO_ROOT / "src/now_playing_desktops/__main__.py",
        "now_playing_desktops.cli",
    )


def test_spotify_windows_calls_dpi_before_cli_import():
    _calls_set_process_dpi_aware_before_import(
        REPO_ROOT / "spotifyWindows.py",
        "now_playing_desktops.cli",
    )


def test_cli_bootstraps_dpi_on_win32_before_heavy_imports():
    cli_path = REPO_ROOT / "src/now_playing_desktops/cli.py"
    text = cli_path.read_text(encoding="utf-8")
    assert "set_process_dpi_aware" in text
    dpi_pos = text.index("set_process_dpi_aware")
    runner_pos = text.index("from now_playing_desktops.runner import")
    assert dpi_pos < runner_pos


@pytest.mark.parametrize(
    "entry",
    [
        "now_playing_desktops.cli:main",
        "now_playing_desktops.cli:main_windows",
    ],
)
def test_console_script_entry_points_reference_dpi(entry: str):
    scripts = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert entry in scripts
    module_name, attr = entry.split(":")
    module_path = REPO_ROOT / "src" / module_name.replace(".", "/")
    module_path = module_path.with_suffix(".py")
    source = module_path.read_text(encoding="utf-8")
    assert "set_process_dpi_aware" in source
    assert f"def {attr}" in source
