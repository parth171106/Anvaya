"""Serve the built console and API on one localhost port for the live pilot."""
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from app.core import config
from app.main import create_app


class ConsoleFiles(StaticFiles):
    async def get_response(self, path, scope):
        url_path = path.replace("\\", "/")
        if url_path == "api" or url_path.startswith("api/"):
            raise HTTPException(404, "API route not found")
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or Path(path).suffix or scope["method"] not in ("GET", "HEAD"):
                raise
            return await super().get_response("index.html", scope)


def create_pilot_app():
    cfg = config.load()
    if cfg.demo_mode:
        raise ValueError("The pilot requires ANVAYA_DEMO_MODE=0")
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        raise RuntimeError("Build the console first: cd frontend && npm run build")
    app = create_app(cfg)
    app.mount("/", ConsoleFiles(directory=dist, html=True), name="console")
    return app
