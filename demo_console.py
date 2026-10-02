"""White Stone v0.2 — console CLI demo.

Runs the CLI commands end-to-end in a temporary directory and prints results.

Run:
    python demo_console.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

SEP = "-" * 60
SCRIPT = Path(__file__).parent / "white_stone.py"


def run(*args, cwd: Path, input_text: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        input=input_text,
    )


def section(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")


with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp)

    # ── 1. Create a 3-of-5 Stone ─────────────────────────────────
    section("1. white-stone create --k 3 --n 5")
    result = run("create", "--secret", "Demo secret value", "--k", "3", "--n", "5", "--name", "Demo Vault", cwd=work)
    print(result.stdout.strip())
    if result.returncode != 0:
        print("STDERR:", result.stderr)
    else:
        files = sorted(p.name for p in work.iterdir())
        print(f"Files created: {files}")

    # ── 2. Open with 3 shards ────────────────────────────────────
    section("2. white-stone open --stone vault.json --shard shard1.txt --shard shard3.txt --shard shard5.txt")
    result = run(
        "open",
        "--stone", str(work / "vault.json"),
        "--shard", str(work / "shard1.txt"),
        "--shard", str(work / "shard3.txt"),
        "--shard", str(work / "shard5.txt"),
        cwd=work,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print("STDERR:", result.stderr)

    # ── 3. Recast ────────────────────────────────────────────────
    section("3. white-stone recast --stone vault.json --shard shard1.txt --shard shard2.txt --shard shard3.txt --out new-vault --k 2 --n 3")
    new_dir = work / "new-vault"
    result = run(
        "recast",
        "--stone", str(work / "vault.json"),
        "--shard", str(work / "shard1.txt"),
        "--shard", str(work / "shard2.txt"),
        "--shard", str(work / "shard3.txt"),
        "--out", str(new_dir),
        "--k", "2", "--n", "3",
        cwd=work,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print("STDERR:", result.stderr)
    else:
        new_files = sorted(p.name for p in new_dir.iterdir())
        print(f"New vault files: {new_files}")

    # ── 4. Open new vault ────────────────────────────────────────
    section("4. Open new vault with 2 shards")
    result = run(
        "open",
        "--stone", str(new_dir / "vault.json"),
        "--shard", str(new_dir / "shard1.txt"),
        "--shard", str(new_dir / "shard2.txt"),
        cwd=work,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print("STDERR:", result.stderr)

    # ── 5. Multi-group Stone ─────────────────────────────────────
    section("5. white-stone create --group Family:2:3 --group Lawyer:1:1 --need 2")
    group_dir = work / "group-vault"
    group_dir.mkdir()
    result = run(
        "create",
        "--secret", "Group demo secret",
        "--group", "Family:2:3",
        "--group", "Lawyer:1:1",
        "--need", "2",
        "--name", "Group Demo",
        "--output-dir", str(group_dir),
        cwd=work,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print("STDERR:", result.stderr)
    else:
        gfiles = sorted(p.name for p in group_dir.iterdir())
        print(f"Files: {gfiles}")

print(f"\n{SEP}\nConsole demo complete.\n{SEP}\n")
