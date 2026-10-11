"""RFC 6962 Merkle tree over ANVAYA leaves (TRD.md §8.1)."""
import hashlib


def leaf_hash(raw_sha256: bytes, seq: int) -> bytes:
    return hashlib.sha256(b"\x00" + raw_sha256 + seq.to_bytes(8, "big")).digest()


def node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:  # largest power of two < n
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def mth(leaves: list[bytes]) -> bytes:
    if len(leaves) == 1:
        return leaves[0]
    k = _split(len(leaves))
    return node(mth(leaves[:k]), mth(leaves[k:]))


def audit_path(leaves: list[bytes], m: int) -> list[bytes]:
    """RFC 6962 §2.1.1 PATH(m, D[n]), leaf-to-root order."""
    if len(leaves) == 1:
        return []
    k = _split(len(leaves))
    if m < k:
        return audit_path(leaves[:k], m) + [mth(leaves[k:])]
    return audit_path(leaves[k:], m - k) + [mth(leaves[:k])]


def root_from_path(leaf: bytes, m: int, n: int, path: list[bytes]) -> bytes:
    """Recompute the root from a leaf and its audit path (RFC 9162 §2.1.3.2)."""
    fn, sn, r = m, n - 1, leaf
    for p in path:
        if fn % 2 == 1 or fn == sn:
            r = node(p, r)
            while fn % 2 == 0 and fn != 0:
                fn, sn = fn >> 1, sn >> 1
        else:
            r = node(r, p)
        fn, sn = fn >> 1, sn >> 1
    return r
