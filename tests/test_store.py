"""Tests for white_stone.store."""

import pytest
from pathlib import Path

from white_stone import WhiteStoneError, create_stone
from white_stone.store import load_stone, load_tessera, load_tesserae, save_stone, save_tessera

SECRET = "store test secret"


def test_save_and_load_stone_roundtrip(tmp_path):
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    path = tmp_path / "vault.json"
    save_stone(stone, path, name="Test Vault")
    loaded, name = load_stone(path)
    assert name == "Test Vault"
    assert loaded.id == stone.id
    assert loaded.group_threshold == stone.group_threshold
    assert loaded.ct == stone.ct


def test_load_stone_without_name(tmp_path):
    stone, _, _ = create_stone(SECRET, 2, 3)
    path = tmp_path / "vault.json"
    save_stone(stone, path)
    loaded, name = load_stone(path)
    assert name is None
    assert loaded.id == stone.id


def test_load_stone_missing_file_raises(tmp_path):
    with pytest.raises(WhiteStoneError) as exc_info:
        load_stone(tmp_path / "nonexistent.json")
    assert exc_info.value.code == "BAD_FORMAT"


def test_load_stone_bad_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(WhiteStoneError) as exc_info:
        load_stone(path)
    assert exc_info.value.code == "BAD_FORMAT"


def test_save_and_load_tessera_roundtrip(tmp_path):
    _, tesserae, _ = create_stone(SECRET, 2, 3)
    path = tmp_path / "shard1.txt"
    save_tessera(tesserae[0], path)
    loaded = load_tessera(path)
    assert loaded == tesserae[0]


def test_load_tessera_missing_file_raises(tmp_path):
    with pytest.raises(WhiteStoneError) as exc_info:
        load_tessera(tmp_path / "missing.txt")
    assert exc_info.value.code == "BAD_FORMAT"


def test_load_tesserae_returns_all(tmp_path):
    _, tesserae, _ = create_stone(SECRET, 2, 3)
    paths = []
    for i, t in enumerate(tesserae):
        p = tmp_path / f"shard{i + 1}.txt"
        save_tessera(t, p)
        paths.append(p)
    loaded = load_tesserae(paths)
    assert loaded == tesserae
