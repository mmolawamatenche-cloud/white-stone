"""White Stone core v0.2 — groups, Recasting, Rehearsal."""

from __future__ import annotations

import base64
import argparse
import getpass
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import nacl.bindings as nb
import nacl.utils
import qrcode
import qrcode.constants
from shamir_mnemonic import MnemonicError, combine_mnemonics, generate_mnemonics
from shamir_mnemonic.share import Share

VERSION = 2
KEY_LEN = 32
MAX_GROUPS = 16
MAX_N = 16


class WhiteStoneError(Exception):
    """A user-safe error with a stable machine-readable code."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True)
class Group:
    name: str
    k: int
    n: int


@dataclass(frozen=True)
class Stone:
    """Encrypted Stone file; safe to store without its tesserae."""

    id: int
    group_threshold: int
    groups: Tuple[Group, ...]
    nonce: str
    ct: str
    protected: bool = False
    previous_id: Optional[int] = None
    v: int = VERSION

    # Convenience shims for single-group code
    @property
    def k(self) -> int:
        return self.groups[0].k

    @property
    def n(self) -> int:
        return self.groups[0].n

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "group_threshold": self.group_threshold,
            "groups": [{"name": g.name, "k": g.k, "n": g.n} for g in self.groups],
            "nonce": self.nonce,
            "ct": self.ct,
            "protected": self.protected,
            "previous_id": self.previous_id,
            "v": self.v,
        }, indent=2)

    @staticmethod
    def from_json(text: str) -> "Stone":
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError
            if "stone" in data:
                data = data["stone"]
            if not isinstance(data, dict):
                raise ValueError
            v = data.get("v", VERSION)
            if v != VERSION:
                raise WhiteStoneError(
                    "UNSUPPORTED_VERSION",
                    f"This Stone was made with a different version (v{v}). Only v{VERSION} is supported.",
                )
            groups = tuple(Group(**g) for g in data["groups"])
            return Stone(
                id=data["id"],
                group_threshold=data["group_threshold"],
                groups=groups,
                nonce=data["nonce"],
                ct=data["ct"],
                protected=data.get("protected", False),
                previous_id=data.get("previous_id"),
                v=v,
            )
        except WhiteStoneError:
            raise
        except (ValueError, TypeError, KeyError) as exc:
            raise WhiteStoneError("BAD_FORMAT", "This is not a valid Stone file.") from exc


@dataclass(frozen=True)
class ParsedTessera:
    id: int
    group_index: int
    group_count: int
    group_threshold: int
    k: int          # member_threshold
    index: int
    words: str


def _aad(stone_id: int, group_threshold: int, groups: Sequence[Group], protected: bool) -> bytes:
    out = bytes([VERSION]) + stone_id.to_bytes(2, "big") + bytes([group_threshold, len(groups)])
    for g in groups:
        out += bytes([g.k, g.n])
    return out + bytes([int(protected)])


def _passphrase_bytes(passphrase: Optional[str]) -> bytes:
    if not passphrase:
        return b""
    if not isinstance(passphrase, str) or not all(32 <= ord(c) <= 126 for c in passphrase):
        raise WhiteStoneError(
            "BAD_INPUT",
            "Use only standard keyboard characters in the passphrase (printable ASCII).",
        )
    return passphrase.encode("ascii")


def _is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _validate_groups(group_threshold: int, groups: Sequence[Group]) -> None:
    if not groups or len(groups) > MAX_GROUPS:
        raise WhiteStoneError("BAD_INPUT", f"Provide 1–{MAX_GROUPS} groups.")
    if not _is_int(group_threshold) or not (1 <= group_threshold <= len(groups)):
        raise WhiteStoneError(
            "BAD_INPUT",
            f"group_threshold must be between 1 and the number of groups ({len(groups)}).",
        )
    for g in groups:
        if not (_is_int(g.k) and _is_int(g.n)) or not (1 <= g.k <= g.n <= MAX_N):
            raise WhiteStoneError("BAD_INPUT", f"Group '{g.name}': use 1 <= k <= n <= {MAX_N}.")
        if g.k == 1 and g.n > 1:
            raise WhiteStoneError(
                "BAD_INPUT",
                f"Group '{g.name}': a 1-of-{g.n} group makes every tessera a full copy. "
                "Use 1-of-1 for a single Keeper.",
            )
    # At least two people must always be required
    min_people = sum(sorted(g.k for g in groups)[:group_threshold])
    if min_people < 2:
        raise WhiteStoneError(
            "BAD_INPUT",
            "At least two people must always be required to open a Stone.",
        )


def _warnings(group_threshold: int, groups: Sequence[Group]) -> List[str]:
    # Warn if losing any single tessera makes the Stone unopenable
    for gi, g in enumerate(groups):
        for lost_gi in range(len(groups)):
            available = [
                (g2.n - (1 if i == lost_gi else 0)) >= g2.k
                for i, g2 in enumerate(groups)
            ]
            if sum(available) < group_threshold:
                return ["If even one Keeper loses their tessera, this Stone can never be opened."]
    return []


def parse_tessera(text: str) -> ParsedTessera:
    """Validate one SLIP-39 tessera phrase."""
    if not isinstance(text, str) or not text.strip():
        raise WhiteStoneError("BAD_FORMAT", "This does not look like a White Stone tessera.")
    words = " ".join(text.lower().split())
    try:
        s = Share.from_mnemonic(words)
    except MnemonicError as exc:
        if "checksum" in str(exc).lower():
            raise WhiteStoneError("BAD_CHECKSUM", "This tessera is damaged or mistyped.") from exc
        raise WhiteStoneError(
            "BAD_FORMAT", "We couldn't read this tessera. Check the words against the card."
        ) from exc
    return ParsedTessera(
        id=s.identifier,
        group_index=s.group_index,
        group_count=s.group_count,
        group_threshold=s.group_threshold,
        k=s.member_threshold,
        index=s.index,
        words=words,
    )


def _as_bytes(secret: str | bytes) -> bytes:
    if isinstance(secret, str):
        return secret.encode("utf-8")
    if isinstance(secret, bytes):
        return secret
    raise WhiteStoneError("BAD_INPUT", "The secret must be text or bytes.")


def _build_stone(
    data: bytes,
    group_threshold: int,
    groups: List[Group],
    passphrase: Optional[str],
) -> Tuple["Stone", List[List[str]], List[str]]:
    if not data:
        raise WhiteStoneError("BAD_INPUT", "The secret cannot be empty.")
    _validate_groups(group_threshold, groups)
    pw = _passphrase_bytes(passphrase)
    warns = _warnings(group_threshold, groups)

    key = nacl.utils.random(KEY_LEN)
    nonce = nacl.utils.random(nb.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES)
    raw_groups = generate_mnemonics(group_threshold, [(g.k, g.n) for g in groups], key, passphrase=pw)
    stone_id = Share.from_mnemonic(raw_groups[0][0]).identifier
    protected = bool(pw)

    ct = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(
        data, _aad(stone_id, group_threshold, groups, protected), nonce, key
    )
    stone = Stone(
        id=stone_id,
        group_threshold=group_threshold,
        groups=tuple(groups),
        nonce=_b64e(nonce),
        ct=_b64e(ct),
        protected=protected,
    )

    # Rehearsal: open with the smallest valid set
    test_flat = [t for i in range(group_threshold) for t in raw_groups[i][: groups[i].k]]
    if join_stone(stone, test_flat, passphrase) != data:
        raise WhiteStoneError("DECRYPT_FAILED", "Rehearsal failed. Nothing was created.")

    return stone, raw_groups, warns


def create_stone_groups(
    secret: str | bytes,
    group_threshold: int,
    groups: Sequence[Group],
    passphrase: Optional[str] = None,
) -> Tuple["Stone", List[List[str]], List[str]]:
    """Create a Stone with multiple groups. Returns (stone, tesserae_by_group, warnings)."""
    return _build_stone(_as_bytes(secret), group_threshold, list(groups), passphrase)


def create_stone(
    secret: str | bytes, k: int, n: int, passphrase: Optional[str] = None
) -> Tuple["Stone", List[str], List[str]]:
    """Single-group convenience wrapper. Returns (stone, flat_tesserae, warnings)."""
    if not (_is_int(k) and _is_int(n)):
        raise WhiteStoneError("BAD_INPUT", "k and n must be whole numbers.")
    stone, by_group, warns = _build_stone(_as_bytes(secret), 1, [Group("Keepers", k, n)], passphrase)
    return stone, by_group[0], warns


def _validated_by_group(
    stone: Stone, tesserae: Iterable[str]
) -> Tuple[List[List[ParsedTessera]], List[dict]]:
    by_group: List[List[ParsedTessera]] = [[] for _ in stone.groups]
    errors: List[dict] = []
    seen: set = set()

    for pos, tessera in enumerate(tesserae):
        try:
            p = parse_tessera(tessera)
            if (
                p.id != stone.id
                or p.group_threshold != stone.group_threshold
                or p.group_count != len(stone.groups)
                or p.group_index >= len(stone.groups)
                or p.k != stone.groups[p.group_index].k
            ):
                raise WhiteStoneError("WRONG_STONE", "This tessera belongs to a different Stone.")
            key = (p.group_index, p.index)
            if key in seen:
                raise WhiteStoneError("DUPLICATE", "This tessera was already added.")
            seen.add(key)
            by_group[p.group_index].append(p)
        except WhiteStoneError as exc:
            errors.append({"index": pos, "code": exc.code, "message": str(exc)})

    return by_group, errors


def join_progress(stone: Stone, tesserae: Iterable[str]) -> dict:
    """Per-group progress for the Joining screen."""
    by_group, errors = _validated_by_group(stone, tesserae)
    group_info = []
    groups_done = 0
    for g, shares in zip(stone.groups, by_group):
        done = len(shares) >= g.k
        if done:
            groups_done += 1
        group_info.append({"name": g.name, "have": len(shares), "need": g.k, "done": done})
    return {
        "valid": sum(len(s) for s in by_group),
        "groups": group_info,
        "groups_done": groups_done,
        "groups_needed": stone.group_threshold,
        "ready": groups_done >= stone.group_threshold,
        "errors": errors,
    }


def join_stone(
    stone: Stone,
    tesserae: Iterable[str],
    passphrase: Optional[str] = None,
    retired_ids: Optional[Iterable[int]] = None,
) -> bytes:
    """Open a Stone using enough valid tesserae across the required groups."""
    if stone.v != VERSION:
        raise WhiteStoneError("UNSUPPORTED_VERSION", "Unsupported Stone version.")
    if retired_ids and stone.id in set(retired_ids):
        raise WhiteStoneError("RETIRED", "This Stone has been retired. Use the new Stone.")
    if stone.protected and not passphrase:
        raise WhiteStoneError("NEEDS_PASSPHRASE", "This Stone also needs its passphrase.")
    pw = _passphrase_bytes(passphrase) if stone.protected else b""

    by_group, errors = _validated_by_group(stone, list(tesserae))
    if errors:
        raise WhiteStoneError(errors[0]["code"], errors[0]["message"], errors=errors)

    satisfied: List[List[ParsedTessera]] = []
    for g, shares in zip(stone.groups, by_group):
        if len(shares) >= g.k:
            satisfied.append(shares[: g.k])

    if len(satisfied) < stone.group_threshold:
        raise WhiteStoneError(
            "NOT_ENOUGH",
            f"{len(satisfied)} of {stone.group_threshold} groups satisfied. More tesserae are needed.",
            groups_done=len(satisfied),
            groups_needed=stone.group_threshold,
        )

    flat_words = [p.words for grp in satisfied for p in grp]
    try:
        key = combine_mnemonics(flat_words, passphrase=pw)
        return nb.crypto_aead_xchacha20poly1305_ietf_decrypt(
            _b64d(stone.ct),
            _aad(stone.id, stone.group_threshold, stone.groups, stone.protected),
            _b64d(stone.nonce),
            key,
        )
    except Exception as exc:
        raise WhiteStoneError(
            "DECRYPT_FAILED",
            "These tesserae could not open the Stone. One may be wrong, the passphrase "
            "may be wrong, or the Stone file was changed.",
        ) from exc


def rehearse(
    stone: Stone,
    tesserae: Iterable[str],
    passphrase: Optional[str] = None,
) -> dict:
    """Try to open the Stone; return {ok: True} or {ok: False, code, message}. Never returns the secret."""
    try:
        join_stone(stone, tesserae, passphrase)
        return {"ok": True}
    except WhiteStoneError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc)}


def recast_stone(
    old_stone: Stone,
    old_tesserae: Iterable[str],
    k: Optional[int] = None,
    n: Optional[int] = None,
    group_threshold: Optional[int] = None,
    groups: Optional[Sequence[Group]] = None,
    old_passphrase: Optional[str] = None,
    new_passphrase: Optional[str] = None,
) -> Tuple["Stone", List[List[str]], List[str], int]:
    """
    Open old_stone, re-encrypt the secret under a new key, issue new tesserae.
    Returns (new_stone, new_tesserae_by_group, warnings, retired_id).
    """
    secret = join_stone(old_stone, old_tesserae, old_passphrase)

    if groups is not None:
        gt = group_threshold if group_threshold is not None else 1
        new_groups = list(groups)
    else:
        if not (_is_int(k) and _is_int(n)):
            raise WhiteStoneError("BAD_INPUT", "Provide either groups or both k and n.")
        gt = 1
        new_groups = [Group("Keepers", k, n)]  # type: ignore[arg-type]

    new_stone, new_by_group, warns = _build_stone(secret, gt, new_groups, new_passphrase)
    new_stone = Stone(
        id=new_stone.id,
        group_threshold=new_stone.group_threshold,
        groups=new_stone.groups,
        nonce=new_stone.nonce,
        ct=new_stone.ct,
        protected=new_stone.protected,
        previous_id=old_stone.id,
    )
    return new_stone, new_by_group, warns, old_stone.id


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

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


def _write_shards(output_dir: Path, by_group: List[List[str]]) -> None:
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

    # Validate before touching the filesystem
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
    _write_shards(output_dir, by_group)

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
    _write_shards(out, new_by_group)

    print(f"Recast complete. Retired Stone id: {retired_id}")
    print(f"New Stone written to {out.resolve()}")
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="White Stone v0.2")
    commands = parser.add_subparsers(dest="command", required=True)

    # create
    cp = commands.add_parser("create", help="encrypt a secret and create tesserae")
    cp.add_argument("--secret", help="secret text (omit to enter without echo)")
    cp.add_argument("--secret-file", type=Path, dest="secret_file", help="read secret from a file")
    cp.add_argument("--k", type=int, default=None, help="tesserae needed (single-group)")
    cp.add_argument("--n", type=int, default=None, help="total tesserae (single-group)")
    cp.add_argument("--group", action="append", metavar="Name:k:n", help="add a group (repeatable)")
    cp.add_argument("--need", type=int, default=None, help="groups needed to open (default 1)")
    cp.add_argument("--name", default="Untitled Stone", help="Stone label")
    cp.add_argument("--output-dir", type=Path, default=Path.cwd(), dest="output_dir")
    cp.set_defaults(handler=_create_command)

    # open
    op = commands.add_parser("open", help="open a vault with enough tesserae")
    op.add_argument("--stone", "--vault", type=Path, required=True, dest="stone", help="Stone JSON file")
    op.add_argument("--shard", type=Path, action="append", required=True)
    op.set_defaults(handler=_open_command)

    # recast
    rp = commands.add_parser("recast", help="re-key a Stone with new tesserae")
    rp.add_argument("--stone", type=Path, required=True, help="existing Stone JSON file")
    rp.add_argument("--shard", type=Path, action="append", required=True)
    rp.add_argument("--out", type=Path, required=True, help="output directory for new Stone")
    rp.add_argument("--k", type=int, default=None)
    rp.add_argument("--n", type=int, default=None)
    rp.add_argument("--group", action="append", metavar="Name:k:n")
    rp.add_argument("--need", type=int, default=None)
    rp.set_defaults(handler=_recast_command)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except WhiteStoneError as exc:
        parser.exit(2, f"white_stone: {exc.code}: {exc}\n")
    except OSError as exc:
        parser.exit(2, f"white_stone: could not access a file: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
