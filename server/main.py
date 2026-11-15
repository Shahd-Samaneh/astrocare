"""AstroCare API (FastAPI).

Dev:   npm run dev     -> uvicorn server.main:app --reload --port 8000 (+ Vite on 5173)
Demo:  npm run start   -> this process also serves the built frontend (app/dist)

Everything runs on localhost. The app never calls the internet.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from server.core import db, live_feed
from server.core.config import DIST_DIR, app_config
from server.core.models import AppStatus
from server.core.seed import seed
from server.core.status import build_status
from server.features.assistant.router import router as assistant_router
from server.features.crew.router import router as crew_router
from server.features.daily.router import router as daily_router
from server.features.monitoring.router import router as monitoring_router
from server.features.relax.router import router as relax_router
from server.features.reports.router import router as reports_router
from server.features.twin.router import router as twin_router
from server.rules.engine import run_rules

log = logging.getLogger("astrocare")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    reseed = bool(app_config().get("simulator", {}).get("reseed_on_start", False))
    if seed(force=reseed):
        log.info("Seeded simulated data")
    run_rules()
    feed = asyncio.create_task(live_feed.run_forever()) if live_feed.feed_enabled() else None
    yield
    if feed:
        feed.cancel()
        with suppress(asyncio.CancelledError):
            await feed


app = FastAPI(title="AstroCare API", version="0.1.0", lifespan=lifespan)

for r in (monitoring_router, daily_router, assistant_router, reports_router, relax_router, twin_router, crew_router):
    app.include_router(r, prefix="/api")


# ---- core endpoints --------------------------------------------------------
@app.get("/api/health", tags=["core"])
def health() -> dict:
    return {"ok": True}


@app.get("/api/status", tags=["core"])
def status() -> AppStatus:
    return build_status()


@app.get("/api/{path:path}", include_in_schema=False)
def api_not_found(path: str):
    raise HTTPException(status_code=404, detail=f"Unknown API route: /api/{path}")


# ---- production: serve the built SPA (app/dist) ------------------------------
@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if not DIST_DIR.exists():
        raise HTTPException(status_code=404, detail="Frontend not built. Run `npm run build` (or use `npm run dev`).")
    candidate = (DIST_DIR / path).resolve()
    if path and candidate.is_file() and DIST_DIR.resolve() in candidate.parents:
        return FileResponse(candidate)
    return FileResponse(DIST_DIR / "index.html")  # SPA fallback for client-side routes
