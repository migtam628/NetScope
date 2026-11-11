from pathlib import Path

import netscope


def test_package_version_matches_version_file():
    root = Path(__file__).resolve().parents[2] / "VERSION"
    assert netscope.__version__ == root.read_text().strip()
