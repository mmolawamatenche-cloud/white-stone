"""White Stone v0.2 test suite — 29 tests."""

import subprocess
import sys
from itertools import combinations
from pathlib import Path

import pytest

from white_stone import (
    Group,
    Stone,
    WhiteStoneError,
    create_stone,
    create_stone_groups,
    join_progress,
    join_stone,
    parse_tessera,
    recast_stone,
    rehearse,
)

SECRET = "recovery words: alpha bravo charlie delta echo"


def code_of(fn, *args, **kwargs):
    with pytest.raises(WhiteStoneError) as exc_info:
        fn(*args, **kwargs)
    return exc_info.value.code


# ---------------------------------------------------------------------------
# Single-group create / open
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("k,n", [(2, 3), (3, 5), (4, 7)])
def test_every_group_of_k_opens_and_every_smaller_group_is_refused(k, n):
    stone, tesserae, _ = create_stone(SECRET, k, n)
    for group in combinations(tesserae, k):
        assert join_stone(stone, group).decode() == SECRET
    for group in combinations(tesserae, k - 1):
        assert code_of(join_stone, stone, group) == "NOT_ENOUGH"


def test_more_than_k_tesserae_also_works():
    stone, tesserae, _ = create_stone(SECRET, 3, 5)
    assert join_stone(stone, tesserae).decode() == SECRET


def test_binary_and_large_secrets():
    secret = bytes(range(256)) * 800
    stone, tesserae, _ = create_stone(secret, 3, 5)
    assert join_stone(stone, tesserae[2:5]) == secret


def test_invalid_fit_values_are_refused():
    for k, n in [(1, 3), (4, 3), (2, 17), (0, 0)]:
        assert code_of(create_stone, SECRET, k, n) == "BAD_INPUT"
    assert code_of(create_stone, SECRET, 2.5, 4) == "BAD_INPUT"
    assert code_of(create_stone, "", 2, 3) == "BAD_INPUT"


def test_k_equal_n_warns():
    _, _, warnings = create_stone(SECRET, 3, 3)
    assert len(warnings) == 1


def test_tessera_is_33_words_and_roundtrips_through_parse():
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    assert len(tesserae[0].split()) == 33
    parsed = parse_tessera(tesserae[0].upper())
    assert parsed.id == stone.id and parsed.k == 2


def test_mistyped_or_junk_tessera_is_caught():
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    words = tesserae[0].split()
    words[5] = "academic" if words[5] != "academic" else "acid"
    assert code_of(join_stone, stone, [" ".join(words), tesserae[1]]) == "BAD_CHECKSUM"
    assert code_of(parse_tessera, "hello world") == "BAD_FORMAT"
    assert code_of(parse_tessera, "") == "BAD_FORMAT"


def test_tessera_from_another_stone_is_refused():
    stone_a, tesserae_a, _ = create_stone(SECRET, 2, 3)
    stone_b, tesserae_b, _ = create_stone("another secret", 2, 3)
    if stone_a.id == stone_b.id:
        pytest.skip("SLIP-39 identifier collision")
    assert code_of(join_stone, stone_a, [tesserae_a[0], tesserae_b[1]]) == "WRONG_STONE"


def test_same_tessera_twice_is_refused():
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    assert code_of(join_stone, stone, [tesserae[0], tesserae[0]]) == "DUPLICATE"


def test_changed_stone_file_never_opens():
    import base64
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    raw = bytearray(base64.urlsafe_b64decode(stone.ct + "=" * (-len(stone.ct) % 4)))
    raw[0] ^= 1
    bad_ct = base64.urlsafe_b64encode(bytes(raw)).decode().rstrip("=")
    tampered = Stone(**{**stone.__dict__, "ct": bad_ct})
    assert code_of(join_stone, tampered, tesserae[:2]) == "DECRYPT_FAILED"


def test_stone_file_json_roundtrip():
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    restored = Stone.from_json(stone.to_json())
    assert join_stone(restored, tesserae[:2]).decode() == SECRET
    assert code_of(Stone.from_json, "not json") == "BAD_FORMAT"


def test_passphrase_protection():
    stone, tesserae, _ = create_stone(SECRET, 2, 3, passphrase="correct horse")
    assert stone.protected
    assert join_stone(stone, tesserae[:2], "correct horse").decode() == SECRET
    assert code_of(join_stone, stone, tesserae[:2]) == "NEEDS_PASSPHRASE"
    assert code_of(join_stone, stone, tesserae[:2], "wrong") == "DECRYPT_FAILED"
    assert code_of(create_stone, SECRET, 2, 3, passphrase="pässword") == "BAD_INPUT"


def test_same_secret_gives_different_ciphertext_each_time():
    first, _, _ = create_stone(SECRET, 2, 3)
    second, _, _ = create_stone(SECRET, 2, 3)
    assert first.ct != second.ct and first.nonce != second.nonce


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def test_two_group_stone_requires_both_groups():
    groups = [Group("Family", 2, 3), Group("Lawyer", 1, 1)]
    stone, by_group, _ = create_stone_groups(SECRET, 2, groups)
    family, lawyer = by_group[0], by_group[1]

    # Both groups satisfied → opens
    assert join_stone(stone, family[:2] + lawyer).decode() == SECRET

    # Only Family satisfied → NOT_ENOUGH
    assert code_of(join_stone, stone, family[:2]) == "NOT_ENOUGH"

    # Only Lawyer satisfied → NOT_ENOUGH
    assert code_of(join_stone, stone, lawyer) == "NOT_ENOUGH"


def test_group_threshold_less_than_total_groups():
    groups = [Group("A", 2, 3), Group("B", 2, 3), Group("C", 2, 3)]
    stone, by_group, _ = create_stone_groups(SECRET, 2, groups)
    # Any 2 of 3 groups should open it
    for chosen in combinations(range(3), 2):
        flat = [t for i in chosen for t in by_group[i][:2]]
        assert join_stone(stone, flat).decode() == SECRET


def test_one_of_one_group_is_allowed():
    groups = [Group("Solo", 1, 1), Group("Partner", 2, 3)]
    stone, by_group, _ = create_stone_groups(SECRET, 2, groups)
    assert join_stone(stone, by_group[0] + by_group[1][:2]).decode() == SECRET


def test_one_of_n_group_is_refused():
    assert code_of(
        create_stone_groups, SECRET, 1, [Group("Bad", 1, 3)]
    ) == "BAD_INPUT"


def test_single_person_always_refused():
    # 1-of-1 single group → only 1 person needed
    assert code_of(create_stone_groups, SECRET, 1, [Group("Solo", 1, 1)]) == "BAD_INPUT"


def test_join_progress_multi_group():
    groups = [Group("Family", 2, 3), Group("Lawyer", 1, 1)]
    stone, by_group, _ = create_stone_groups(SECRET, 2, groups)
    family, lawyer = by_group[0], by_group[1]

    progress = join_progress(stone, family[:1])
    assert progress["groups_done"] == 0
    assert progress["ready"] is False

    progress = join_progress(stone, family[:2] + lawyer)
    assert progress["groups_done"] == 2
    assert progress["ready"] is True


# ---------------------------------------------------------------------------
# join_progress (single-group, detailed)
# ---------------------------------------------------------------------------

def test_joining_progress_counts_only_valid_distinct_tesserae():
    stone, tesserae, _ = create_stone(SECRET, 3, 5)
    _, other_tesserae, _ = create_stone("x", 3, 5)
    progress = join_progress(
        stone, [tesserae[0], tesserae[0], other_tesserae[1], "junk", tesserae[2]]
    )
    assert progress["valid"] == 2
    assert progress["ready"] is False
    codes = sorted(e["code"] for e in progress["errors"])
    assert "BAD_FORMAT" in codes and "DUPLICATE" in codes
    assert join_progress(stone, tesserae[:3])["ready"] is True


# ---------------------------------------------------------------------------
# Rehearsal
# ---------------------------------------------------------------------------

def test_rehearse_returns_ok_true_with_enough_tesserae():
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    result = rehearse(stone, tesserae[:2])
    assert result == {"ok": True}


def test_rehearse_returns_ok_false_without_enough_tesserae():
    stone, tesserae, _ = create_stone(SECRET, 3, 5)
    result = rehearse(stone, tesserae[:2])
    assert result["ok"] is False
    assert result["code"] == "NOT_ENOUGH"


def test_rehearse_never_returns_secret():
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    result = rehearse(stone, tesserae[:2])
    assert SECRET not in str(result)


# ---------------------------------------------------------------------------
# Recasting
# ---------------------------------------------------------------------------

def test_recast_produces_new_stone_with_same_secret():
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    new_stone, new_by_group, _, retired_id = recast_stone(stone, tesserae[:2], k=3, n=5)
    assert retired_id == stone.id
    assert new_stone.id != stone.id
    assert new_stone.previous_id == stone.id
    assert join_stone(new_stone, new_by_group[0][:3]).decode() == SECRET


def test_recast_old_stone_still_opens_with_old_tesserae():
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    recast_stone(stone, tesserae[:2], k=2, n=3)
    # Old stone + old tesserae still work (until file is deleted)
    assert join_stone(stone, tesserae[:2]).decode() == SECRET


def test_recast_retired_id_blocks_old_stone():
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    _, _, _, retired_id = recast_stone(stone, tesserae[:2], k=2, n=3)
    assert code_of(join_stone, stone, tesserae[:2], retired_ids={retired_id}) == "RETIRED"


def test_recast_with_groups():
    stone, tesserae, _ = create_stone(SECRET, 2, 3)
    new_groups = [Group("Family", 2, 3), Group("Lawyer", 1, 1)]
    new_stone, new_by_group, _, _ = recast_stone(
        stone, tesserae[:2], group_threshold=2, groups=new_groups
    )
    flat = new_by_group[0][:2] + new_by_group[1]
    assert join_stone(new_stone, flat).decode() == SECRET


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

SCRIPT = Path(__file__).resolve().parents[1] / "white_stone.py"


def test_cli_create_and_open(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "create",
         "--secret", "TEST SECRET", "--k", "3", "--n", "5", "--name", "Test Stone"],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "vault.json").is_file()
    for i in range(1, 6):
        assert (tmp_path / f"shard{i}.txt").is_file()
        assert (tmp_path / f"shard{i}.png").is_file()

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "open",
         "--stone", str(tmp_path / "vault.json"),
         "--shard", str(tmp_path / "shard1.txt"),
         "--shard", str(tmp_path / "shard3.txt"),
         "--shard", str(tmp_path / "shard5.txt")],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "TEST SECRET" in result.stdout


def test_cli_rejects_invalid_fit_before_creating_outputs(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "create",
         "--secret", "unused", "--k", "3", "--n", "1000000000"],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "BAD_INPUT" in result.stderr
    assert not (tmp_path / "vault.json").exists()


def test_cli_create_with_groups(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "create",
         "--secret", "GROUP SECRET",
         "--group", "Family:2:3", "--group", "Lawyer:1:1", "--need", "2"],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    # 3 Family + 1 Lawyer = 4 shards
    for i in range(1, 5):
        assert (tmp_path / f"shard{i}.txt").is_file()


def test_cli_recast(tmp_path):
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    subprocess.run(
        [sys.executable, str(SCRIPT), "create",
         "--secret", "RECAST SECRET", "--k", "2", "--n", "3"],
        cwd=old_dir, capture_output=True, check=True,
    )
    new_dir = tmp_path / "new"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "recast",
         "--stone", str(old_dir / "vault.json"),
         "--shard", str(old_dir / "shard1.txt"),
         "--shard", str(old_dir / "shard2.txt"),
         "--out", str(new_dir),
         "--k", "2", "--n", "3"],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (new_dir / "vault.json").is_file()
