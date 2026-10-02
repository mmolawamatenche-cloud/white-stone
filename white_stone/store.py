"""White Stone file store — save and load Stone JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .core import Stone, WhiteStoneError


def save_stone(stone: Stone, path: Path, name: Optional[str] = None) -> None:
    """Write a Stone (and optional display name) to a JSON file."""
    payload: dict = {"stone": json.loads(stone.to_json())}
    if name:
        payload["name"] = name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_stone(path: Path) -> tuple[Stone, Optional[str]]:
    """
    Read a Stone JSON file.
    Returns (stone, name) where name may be None if not stored.
    Raises WhiteStoneError on any read or parse failure.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WhiteStoneError("BAD_FORMAT", f"Could not read Stone file: {exc}") from exc
    stone = Stone.from_json(text)
    name: Optional[str] = None
    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            name = data["name"]
    except json.JSONDecodeError:
        pass
    return stone, name


def save_tessera(tessera: str, path: Path) -> None:
    """Write a single tessera phrase to a text file."""
    path.write_text(tessera + "\n", encoding="utf-8")


def load_tessera(path: Path) -> str:
    """Read a tessera phrase from a text file."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise WhiteStoneError("BAD_FORMAT", f"Could not read tessera file: {exc}") from exc


def load_tesserae(paths: list[Path]) -> list[str]:
    """Read multiple tessera files, returning a flat list of phrases."""
    return [load_tessera(p) for p in paths]
