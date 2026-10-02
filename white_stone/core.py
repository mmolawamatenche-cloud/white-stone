"""White Stone core v0.2 — groups, Recasting, Rehearsal."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

import nacl.bindings as nb
import nacl.utils
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
    k: int
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
        raise WhiteStoneError("BAD_INPUT", f"Provide 1\u2013{MAX_GROUPS} groups.")
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
    min_people = sum(sorted(g.k for g in groups)[:group_threshold])
    if min_people < 2:
        raise WhiteStoneError(
            "BAD_INPUT",
            "At least two people must always be required to open a Stone.",
        )


def _warnings(group_threshold: int, groups: Sequence[Group]) -> List[str]:
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
) -> Tuple[Stone, List[List[str]], List[str]]:
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

    test_flat = [t for i in range(group_threshold) for t in raw_groups[i][: groups[i].k]]
    if join_stone(stone, test_flat, passphrase) != data:
        raise WhiteStoneError("DECRYPT_FAILED", "Rehearsal failed. Nothing was created.")

    return stone, raw_groups, warns


def create_stone_groups(
    secret: str | bytes,
    group_threshold: int,
    groups: Sequence[Group],
    passphrase: Optional[str] = None,
) -> Tuple[Stone, List[List[str]], List[str]]:
    """Create a Stone with multiple groups. Returns (stone, tesserae_by_group, warnings)."""
    return _build_stone(_as_bytes(secret), group_threshold, list(groups), passphrase)


def create_stone(
    secret: str | bytes, k: int, n: int, passphrase: Optional[str] = None
) -> Tuple[Stone, List[str], List[str]]:
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
    """Try to open the Stone without revealing the secret."""
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
) -> Tuple[Stone, List[List[str]], List[str], int]:
    """Re-encrypt the secret under a new key with new tesserae."""
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
