"""NetScope X1 diagnostic engine, API and simulator."""
from pathlib import Path


def _version() -> str:
    try:  # repository checkout: VERSION is the single source of truth
        return (Path(__file__).resolve().parents[2] / "VERSION").read_text().strip()
    except OSError:
        pass
    try:  # installed package
        from importlib.metadata import version
        return version("netscope")
    except Exception:
        return "0.0.0"


__version__ = _version()
