import hashlib

import pytest

from app.vault.merkle import audit_path, leaf_hash, mth, node, root_from_path


def reference_root(leaves):
    """Independent construction: right-fold the perfect subtrees given by n's binary decomposition."""
    subtrees, i, n = [], 0, len(leaves)
    for bit in reversed(range(n.bit_length())):
        size = 1 << bit
        if n & size:
            level = leaves[i:i + size]
            while len(level) > 1:
                level = [node(level[j], level[j + 1]) for j in range(0, len(level), 2)]
            subtrees.append(level[0])
            i += size
    root = subtrees[-1]
    for t in reversed(subtrees[:-1]):
        root = node(t, root)
    return root


def leaves(n):
    return [leaf_hash(hashlib.sha256(bytes([i])).digest(), i + 1) for i in range(n)]


@pytest.mark.parametrize("n", range(1, 18))
def test_root_matches_reference(n):
    assert mth(leaves(n)) == reference_root(leaves(n))


def test_rfc6962_known_answers():
    # Certificate Transparency test vectors: leaf = SHA256(0x00 || data).
    data = ["", "00", "10", "2021", "3031", "40414243", "5051525354555657", "606162636465666768696a6b6c6d6e6f"]
    ls = [hashlib.sha256(b"\x00" + bytes.fromhex(d)).digest() for d in data]
    roots = ["6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
             "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
             "aeb6bcfe274b70a14fb067a5e5578264db0fa9b51af5e0ba159158f329e06e77",
             "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
             "4e3bbb1f7b478dcfe71fb631631519a3bca12c9aefca1612bfce4c13a86264d4",
             "76e67dadbcdf1e10e1b74ddc608abd2f98dfb16fbce75277b5232a127f2087ef",
             "ddb89be403809e325750d3d263cd78929c2942b7942a34b77e122c9594a74c8c",
             "5dc9da79a70659a9ad559cb701ded9a2ab9d823aad2f4960cfe370eff4604328"]
    assert [mth(ls[:n]).hex() for n in range(1, 9)] == roots


@pytest.mark.parametrize("n", range(1, 18))
def test_audit_paths_verify(n):
    ls, root = leaves(n), mth(leaves(n))
    for m in range(n):
        path = audit_path(ls, m)
        assert root_from_path(ls[m], m, n, path) == root


def test_modified_leaf_fails():
    ls = leaves(16)
    root, path = mth(ls), audit_path(ls, 7)
    bad = leaf_hash(hashlib.sha256(b"tampered").digest(), 8)
    assert root_from_path(bad, 7, 16, path) != root
    assert len(path) == 4
