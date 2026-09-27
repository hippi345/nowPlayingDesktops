from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def test_editable_install_exposes_package_and_console(tmp_path: Path):
    venv_dir = tmp_path / "venv"
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        pytest.skip("python venv module unavailable in this environment")

    python = _venv_python(venv_dir)
    subprocess.run(
        [str(python), "-m", "pip", "install", "-e", str(REPO_ROOT)],
        check=True,
        capture_output=True,
    )

    subprocess.run(
        [str(python), "-c", "import now_playing_desktops"],
        check=True,
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        [str(python), "-m", "now_playing_desktops", "--help"],
        check=True,
        cwd=tmp_path,
        capture_output=True,
    )
    script = (
        venv_dir / "Scripts" / "now-playing.exe"
        if sys.platform == "win32"
        else venv_dir / "bin" / "now-playing"
    )
    assert script.is_file()
    subprocess.run([str(script), "--help"], check=True, cwd=tmp_path, capture_output=True)
