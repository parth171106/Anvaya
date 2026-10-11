"""Ed25519 keys as raw 32-byte seeds under /data/keys (TRD.md §8.3). Kept across demo reset."""
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

NAMES = ("primary", "witness-ntro", "witness-certin")


def load_or_create_keys(keys_dir: Path) -> dict[str, Ed25519PrivateKey]:
    keys_dir = Path(keys_dir)
    keys_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(keys_dir, 0o700)
    keys = {}
    for name in NAMES:
        f = keys_dir / f"{name}.ed25519"
        if not f.exists():
            seed = Ed25519PrivateKey.generate().private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
            f.write_bytes(seed)
            os.chmod(f, 0o600)
        keys[name] = Ed25519PrivateKey.from_private_bytes(f.read_bytes())
    return keys


def pub_bytes(key: Ed25519PrivateKey | Ed25519PublicKey) -> bytes:
    pub = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw)


def fingerprint(key) -> str:
    return hashlib.sha256(pub_bytes(key)).hexdigest()[:16]
