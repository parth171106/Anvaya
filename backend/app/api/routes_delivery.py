from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.deps import C
from app.api.errors import ApiError
from app.api.schemas import DeliveryStatus, ParquetExport, RetentionReport
from app.delivery.parquet import export_parquet, list_exports
from app.delivery.retention import build_report

router = APIRouter(prefix="/api")


@router.get("/delivery/status", response_model=DeliveryStatus)
async def status(c: C):
    return {"siem": c.siem.status(), "lake": {"exports": list_exports(c.cfg.data_dir / "lake")},
            "retention": {"available": True}}


class ExportReq(BaseModel):
    from_ms: int | None = None
    to_ms: int | None = None


@router.post("/export/parquet", response_model=ParquetExport)
async def parquet(request: Request, c: C, req: ExportReq | None = None):
    req = req or ExportReq()
    if c.cfg.multi_user and len(list_exports(c.cfg.data_dir / "lake")) >= 5:
        raise ApiError(409, "export_limit", "This pilot allows five stored exports per workspace. Contact the operator to remove old exports.")
    try:
        out = export_parquet(c.repo, c.cfg.data_dir / "lake", req.from_ms, req.to_ms)
    except OSError:
        raise ApiError(503, "dependency_unavailable", "Couldn't write to the data lake folder. Check that /data/lake "
                                                      "is writable.")
    principal = getattr(request.state, "principal", None)
    actor = principal["username"] if principal else "analyst@ntro-demo"
    c.repo.audit(c.clock.now_ms(), actor, "export.parquet", out["file"], {"rows": out["rows"]})
    return out


@router.get("/reports/retention", response_model=RetentionReport)
async def retention(c: C):
    return build_report(c.repo, c.clock.now_ms(), demo_mode=c.cfg.demo_mode)
