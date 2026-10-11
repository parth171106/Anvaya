from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import C
from app.api.errors import ApiError
from app.api.schemas import DemoState, Ok, Reseal, Started
from app.demo.controller import DemoConflict

router = APIRouter(prefix="/api/demo")


def demo(c):
    if not c.cfg.demo_mode:
        raise ApiError(403, "demo_disabled", "Demo routes need ANVAYA_DEMO_MODE=1")
    return c.demo


def run(fn, *a):
    try:
        return fn(*a)
    except DemoConflict as e:
        raise ApiError(409, "conflict", str(e))
    except ValueError as e:
        raise ApiError(422, "validation_error", str(e))


@router.get("/state", response_model=DemoState)
async def state(c: C):
    return c.demo.state() if c.cfg.demo_mode else {"demo_mode": False}


@router.post("/reset", response_model=Ok)
async def reset(c: C):
    d = demo(c)
    try:
        return await d.reset()
    except RuntimeError as e:
        raise ApiError(500, "reset_failed", str(e))


class StartReq(BaseModel):
    speed: int | None = None


@router.post("/scenario/start", status_code=202, response_model=Started)
async def start(c: C, req: StartReq | None = None):
    return run(demo(c).start, req.speed if req else None)


@router.post("/inject-unknown", status_code=202)
async def inject(c: C):
    return run(demo(c).inject_unknown)


class SilenceReq(BaseModel):
    device: str
    silent: bool


@router.post("/silence")
async def silence(req: SilenceReq, c: C):
    return run(demo(c).silence, req.device, req.silent)


@router.post("/tamper")
async def tamper(c: C):
    return run(demo(c).tamper)


@router.post("/reseal", response_model=Reseal)
async def reseal(c: C):
    return run(demo(c).reseal)


class SpeedReq(BaseModel):
    speed: int


@router.post("/speed")
async def speed(req: SpeedReq, c: C):
    return run(demo(c).set_speed, req.speed)
