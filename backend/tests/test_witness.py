import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.vault.keys import pub_bytes
from app.vault.ledger import make_head
from app.vault.witness import ZERO, InProcessWitness, WitnessRejected

PRIMARY = Ed25519PrivateKey.generate()


def signed(batch_id, prev):
    head = make_head(batch_id, bytes([batch_id]) * 32, prev)
    return head, PRIMARY.sign(head)


@pytest.fixture
def w(tmp_path):
    w = InProcessWitness("witness-ntro", tmp_path / "w.db", Ed25519PrivateKey.generate())
    yield w
    w.close()


def test_cosigns_chain(w):
    h1, s1 = signed(1, ZERO)
    cosig = w.cosign(1, h1, ZERO, s1, pub_bytes(PRIMARY))
    w.key.public_key().verify(cosig, h1)
    h2, s2 = signed(2, h1)
    w.cosign(2, h2, h1, s2, pub_bytes(PRIMARY))
    assert w.head_for(2) == h2 and w.last_batch() == 2


def test_rejects_bad_signature(w):
    h1, _ = signed(1, ZERO)
    with pytest.raises(WitnessRejected, match="bad_signature"):
        w.cosign(1, h1, ZERO, Ed25519PrivateKey.generate().sign(h1), pub_bytes(PRIMARY))
    assert w.head_for(1) is None


def test_rejects_prev_head_gap(w):
    h1, s1 = signed(1, ZERO)
    w.cosign(1, h1, ZERO, s1, pub_bytes(PRIMARY))
    h3, s3 = signed(3, h1)  # batch 2 never seen
    with pytest.raises(WitnessRejected, match="prev_head_gap"):
        w.cosign(3, h3, h1, s3, pub_bytes(PRIMARY))


def test_never_overwrites(w):
    h1, s1 = signed(1, ZERO)
    w.cosign(1, h1, ZERO, s1, pub_bytes(PRIMARY))
    other = make_head(1, b"\x09" * 32, ZERO)
    with pytest.raises(WitnessRejected):
        w.cosign(1, other, ZERO, PRIMARY.sign(other), pub_bytes(PRIMARY))
    assert w.head_for(1) == h1
