import hashlib


def raw_id(seq: int, raw_sha256: bytes) -> str:
    return "r-" + hashlib.sha256(seq.to_bytes(8, "big") + raw_sha256).hexdigest()[:12]


def event_id(raw_id_: str) -> str:
    return "e-" + raw_id_[2:]


def group_id(shape_signature: str) -> str:
    return "qg-" + hashlib.sha256(shape_signature.encode()).hexdigest()[:8]


def seq_id(prefix: str, n: int) -> str:  # inc-0001, dr-0001, rp-0001
    return f"{prefix}-{n:04d}"
