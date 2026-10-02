"""White Stone v0.2 — API demo.

Run:
    python demo.py
"""

from white_stone import (
    Group,
    create_stone,
    create_stone_groups,
    join_progress,
    join_stone,
    rehearse,
    recast_stone,
)

SEP = "-" * 60


def section(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")


# ── 1. Simple 3-of-5 Stone ───────────────────────────────────────
section("1. Create a simple 3-of-5 Stone")
stone, tesserae, warnings = create_stone("My important secret", k=3, n=5)
print(f"Stone id   : {stone.id}")
print(f"Groups     : {[{'name': g.name, 'k': g.k, 'n': g.n} for g in stone.groups]}")
print(f"Tesserae   : {len(tesserae)} phrases, first 6 words: {' '.join(tesserae[0].split()[:6])}…")
print(f"Warnings   : {warnings or 'none'}")

# ── 2. Join progress ─────────────────────────────────────────────
section("2. Join progress (2 of 3 needed)")
progress = join_progress(stone, tesserae[:2])
print(f"Valid      : {progress['valid']}")
print(f"Ready      : {progress['ready']}")
print(f"Groups     : {progress['groups']}")

# ── 3. Open with exactly k tesserae ──────────────────────────────
section("3. Open with exactly 3 tesserae")
secret = join_stone(stone, tesserae[:3])
print(f"Revealed   : {secret.decode()}")

# ── 4. Rehearsal ─────────────────────────────────────────────────
section("4. Rehearsal (does not reveal the secret)")
print(f"With 3     : {rehearse(stone, tesserae[:3])}")
print(f"With 2     : {rehearse(stone, tesserae[:2])}")

# ── 5. Multi-group Stone ─────────────────────────────────────────
section("5. Create a grouped Stone: Family 2-of-3 AND Lawyer 1-of-1")
groups = [Group("Family", 2, 3), Group("Lawyer", 1, 1)]
g_stone, by_group, g_warnings = create_stone_groups("Family vault secret", group_threshold=2, groups=groups)
family_shards, lawyer_shards = by_group[0], by_group[1]
print(f"Stone id   : {g_stone.id}")
print(f"Groups     : {[{'name': g.name, 'k': g.k, 'n': g.n} for g in g_stone.groups]}")

g_progress = join_progress(g_stone, family_shards[:2] + lawyer_shards)
print(f"Progress   : groups_done={g_progress['groups_done']}, ready={g_progress['ready']}")

g_secret = join_stone(g_stone, family_shards[:2] + lawyer_shards)
print(f"Revealed   : {g_secret.decode()}")

# ── 6. Recasting ─────────────────────────────────────────────────
section("6. Recast the simple Stone (new key, new tesserae)")
new_stone, new_by_group, _, retired_id = recast_stone(stone, tesserae[:3], k=2, n=3)
print(f"Retired id : {retired_id}")
print(f"New id     : {new_stone.id}")
print(f"previous_id: {new_stone.previous_id}")
new_secret = join_stone(new_stone, new_by_group[0][:2])
print(f"Revealed   : {new_secret.decode()}")

print(f"\n{SEP}\nAll demos passed.\n{SEP}\n")
