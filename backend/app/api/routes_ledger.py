from fastapi import APIRouter

from app.api.deps import C
from app.api.errors import ApiError, not_found
from app.api.schemas import BatchPage, Items, RecordVerify, VerifyResult
from app.vault.keys import fingerprint
from app.vault.witness import LABELS

router = APIRouter(prefix="/api")


@router.post("/ledger/verify/{raw_id}", response_model=RecordVerify)
async def verify_record(raw_id: str, c: C):
    try:
        r = c.ledger.verify_record(raw_id)
    except KeyError:
        raise not_found("Raw record")
    if r is None:
        raise ApiError(409, "conflict", "This record isn't sealed yet.")
    return r


@router.get("/ledger/batches", response_model=BatchPage)
async def batches(c: C, limit: int = 50, before_batch: int | None = None):
    rows = c.repo.batches_page(limit, before_batch)
    sigs = c.repo.witness_sigs([r["batch_id"] for r in rows])
    cols = ("batch_id", "first_seq", "last_seq", "leaf_count", "merkle_root", "prev_head", "head", "signature",
            "sealed_at")
    items = [{**{k: r[k] for k in cols}, "resealed": bool(r["resealed"]),
              "witnesses": [{"name": w.name, "cosigned": sigs.get(r["batch_id"], {}).get(w.name, False)}
                            for w in c.witnesses]} for r in rows]
    return {"items": items, "primary_key_fingerprint": c.ledger.fp}


@router.post("/ledger/verify", response_model=VerifyResult)
async def verify_all(c: C):
    return c.ledger.verify_all()


@router.get("/witnesses", response_model=Items)
async def witnesses(c: C):
    last = c.repo.last_batch()
    top = last["batch_id"] if last else 0
    return {"items": [{"name": w.name, "label": LABELS[w.name], "pubkey_fingerprint": fingerprint(w.key),
                       "last_cosigned_batch": w.last_batch(), "status": "ok" if w.last_batch() == top else "degraded"}
                      for w in c.witnesses]}
