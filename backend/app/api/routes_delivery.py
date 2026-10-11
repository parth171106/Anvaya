from fastapi import APIRouter
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
async def parquet(c: C, req: ExportReq | None = None):
    req = req or ExportReq()
    try:
        out = export_parquet(c.repo, c.cfg.data_dir / "lake", req.from_ms, req.to_ms)
    except OSError:
        raise ApiError(503, "dependency_unavailable", "Couldn't write to the data lake folder. Check that /data/lake "
                                                      "is writable.")
    c.repo.audit(c.clock.now_ms(), "analyst@ntro-demo", "export.parquet", out["file"], {"rows": out["rows"]})
    return out


@router.get("/reports/retention", response_model=RetentionReport)
async def retention(c: C):
    return build_report(c.repo, c.clock.now_ms())
