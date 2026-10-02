"""White Stone CLI — create, open, recast."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import qrcode
import qrcode.constants

from .core import (
    Group,
    Stone,
    WhiteStoneError,
    _validate_groups,
    create_stone_groups,
    join_stone,
    recast_stone,
)


def _parse_group_specs(specs: List[str]) -> List[Group]:
    groups = []
    for spec in specs:
        parts = spec.split(":")
        if len(parts) != 3:
            raise WhiteStoneError("BAD_INPUT", f"--group must be Name:k:n, got '{spec}'.")
        name, k_s, n_s = parts
        try:
            groups.append(Group(name, int(k_s), int(n_s)))
        except ValueError:
            raise WhiteStoneError("BAD_INPUT", f"k and n must be integers in '{spec}'.")
    return groups


def write_shards(output_dir: Path, by_group: List[List[str]]) -> None:
    shard_num = 1
    for group_shards in by_group:
        for tessera in group_shards:
            stem = f"shard{shard_num}"
            (output_dir / f"{stem}.txt").write_text(tessera + "\n", encoding="utf-8")
            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=8, border=4
            )
            qr.add_data(tessera)
            qr.make(fit=True)
            qr.make_image(fill_color="black", back_color="white").save(output_dir / f"{stem}.png")
            shard_num += 1


def _create_command(args: argparse.Namespace) -> int:
    if args.group:
        groups = _parse_group_specs(args.group)
        group_threshold = args.need if args.need is not None else 1
    else:
        if args.k is None or args.n is None:
            raise WhiteStoneError("BAD_INPUT", "Provide --k and --n, or one or more --group specs.")
        groups = [Group("Keepers", args.k, args.n)]
        group_threshold = 1

    _validate_groups(group_threshold, groups)

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    total_shards = sum(g.n for g in groups)
    outputs = [output_dir / "vault.json"]
    for i in range(1, total_shards + 1):
        outputs += [output_dir / f"shard{i}.txt", output_dir / f"shard{i}.png"]
    existing = [p.name for p in outputs if p.exists()]
    if existing:
        raise WhiteStoneError(
            "OUTPUT_EXISTS",
            f"Refusing to overwrite: {', '.join(existing)}. Use an empty output directory.",
        )

    if args.secret_file:
        secret: str = args.secret_file.read_text(encoding="utf-8").rstrip("\n")
    elif args.secret is not None:
        secret = args.secret
    else:
        secret = getpass.getpass("Secret: ")

    stone, by_group, warnings = create_stone_groups(secret, group_threshold, groups)
    vault_data = {"name": args.name, "stone": json.loads(stone.to_json())}
    (output_dir / "vault.json").write_text(json.dumps(vault_data, indent=2), encoding="utf-8")
    write_shards(output_dir, by_group)

    summary = ", ".join(f"{g.name} {g.k}/{g.n}" for g in groups)
    print(f"Created {args.name} (need {stone.group_threshold} of: {summary}) in {output_dir.resolve()}")
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)
    return 0


def _open_command(args: argparse.Namespace) -> int:
    try:
        stone = Stone.from_json(args.stone.read_text(encoding="utf-8"))
        tesserae = [p.read_text(encoding="utf-8").strip() for p in args.shard]
    except (OSError, UnicodeError) as exc:
        raise WhiteStoneError("BAD_FORMAT", f"Could not read an input file: {exc}") from exc

    passphrase = getpass.getpass("Stone passphrase: ") if stone.protected else None
    secret = join_stone(stone, tesserae, passphrase)
    try:
        revealed = secret.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WhiteStoneError(
            "BAD_FORMAT", "This Stone contains binary data and cannot be displayed as text."
        ) from exc
    print("WHITE STONE REVEALED")
    print(revealed)
    return 0


def _recast_command(args: argparse.Namespace) -> int:
    try:
        old_stone = Stone.from_json(args.stone.read_text(encoding="utf-8"))
        tesserae = [p.read_text(encoding="utf-8").strip() for p in args.shard]
    except (OSError, UnicodeError) as exc:
        raise WhiteStoneError("BAD_FORMAT", f"Could not read an input file: {exc}") from exc

    old_passphrase = getpass.getpass("Old Stone passphrase (Enter to skip): ") if old_stone.protected else None

    if args.group:
        groups = _parse_group_specs(args.group)
        group_threshold = args.need if args.need is not None else 1
    else:
        if args.k is None or args.n is None:
            raise WhiteStoneError("BAD_INPUT", "Provide --k and --n, or one or more --group specs.")
        groups = [Group("Keepers", args.k, args.n)]
        group_threshold = 1

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    new_stone, new_by_group, warnings, retired_id = recast_stone(
        old_stone, tesserae,
        group_threshold=group_threshold, groups=groups,
        old_passphrase=old_passphrase,
    )
    vault_data = {"stone": json.loads(new_stone.to_json())}
    (out / "vault.json").write_text(json.dumps(vault_data, indent=2), encoding="utf-8")
    write_shards(out, new_by_group)

    print(f"Recast complete. Retired Stone id: {retired_id}")
    print(f"New Stone written to {out.resolve()}")
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="White Stone v0.2")
    commands = parser.add_subparsers(dest="command", required=True)

    cp = commands.add_parser("create", help="encrypt a secret and create tesserae")
    cp.add_argument("--secret", help="secret text (omit to enter without echo)")
    cp.add_argument("--secret-file", type=Path, dest="secret_file", help="read secret from a file")
    cp.add_argument("--k", type=int, default=None)
    cp.add_argument("--n", type=int, default=None)
    cp.add_argument("--group", action="append", metavar="Name:k:n")
    cp.add_argument("--need", type=int, default=None)
    cp.add_argument("--name", default="Untitled Stone")
    cp.add_argument("--output-dir", type=Path, default=Path.cwd(), dest="output_dir")
    cp.set_defaults(handler=_create_command)

    op = commands.add_parser("open", help="open a vault with enough tesserae")
    op.add_argument("--stone", "--vault", type=Path, required=True, dest="stone")
    op.add_argument("--shard", type=Path, action="append", required=True)
    op.set_defaults(handler=_open_command)

    rp = commands.add_parser("recast", help="re-key a Stone with new tesserae")
    rp.add_argument("--stone", type=Path, required=True)
    rp.add_argument("--shard", type=Path, action="append", required=True)
    rp.add_argument("--out", type=Path, required=True)
    rp.add_argument("--k", type=int, default=None)
    rp.add_argument("--n", type=int, default=None)
    rp.add_argument("--group", action="append", metavar="Name:k:n")
    rp.add_argument("--need", type=int, default=None)
    rp.set_defaults(handler=_recast_command)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except WhiteStoneError as exc:
        parser.exit(2, f"white_stone: {exc.code}: {exc}\n")
    except OSError as exc:
        parser.exit(2, f"white_stone: could not access a file: {exc}\n")
