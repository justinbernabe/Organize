"""FastAPI web app — API + WebSocket + static UI for file organizer."""
import asyncio
import datetime
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    load_config, save_config, make_folder,
    load_run_log, append_run_log, DEFAULT_SETTINGS,
)
from organizer import organize_folder, ProgressEvent
from scheduler import start_scheduler, stop_scheduler, sync_jobs, get_next_run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("server")

# ── WebSocket connection manager ─────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

manager = ConnectionManager()

# ── Running jobs tracker ─────────────────────────────────────────────────

_running_jobs: Dict[str, dict] = {}  # job_id → {folder_id, status, ...}


# ── Scheduled job runner (called by APScheduler) ─────────────────────────

async def _run_organize_job(folder_id: str, folder_path: str):
    """Execute organize for a folder (scheduled or manual trigger)."""
    cfg = load_config()
    settings = cfg.get("settings", {})

    job_id = uuid.uuid4().hex[:12]
    _running_jobs[job_id] = {"folder_id": folder_id, "status": "running"}

    await manager.broadcast({
        "type": "job_start", "job_id": job_id,
        "folder_id": folder_id, "folder_path": folder_path,
    })

    loop = asyncio.get_event_loop()

    def on_event(event: ProgressEvent):
        data = event.to_dict()
        data["job_id"] = job_id
        data["folder_id"] = folder_id
        asyncio.run_coroutine_threadsafe(manager.broadcast(data), loop)

    try:
        result = await loop.run_in_executor(
            None, lambda: organize_folder(
                folder_path, settings=settings, on_event=on_event, dry_run=False
            )
        )
        entry = {
            "job_id": job_id,
            "folder_id": folder_id,
            "folder_path": folder_path,
            "timestamp": datetime.datetime.now().isoformat(),
            "result": result.to_dict(),
            "status": "completed",
        }
        append_run_log(entry)
        _running_jobs[job_id] = {"folder_id": folder_id, "status": "completed"}

        await manager.broadcast({
            "type": "job_complete", "job_id": job_id,
            "folder_id": folder_id, **result.to_dict(),
        })
    except Exception as e:
        log.exception(f"Organize failed for {folder_path}")
        entry = {
            "job_id": job_id,
            "folder_id": folder_id,
            "folder_path": folder_path,
            "timestamp": datetime.datetime.now().isoformat(),
            "status": "error",
            "error": str(e),
        }
        append_run_log(entry)
        _running_jobs[job_id] = {"folder_id": folder_id, "status": "error", "error": str(e)}

        await manager.broadcast({
            "type": "job_error", "job_id": job_id,
            "folder_id": folder_id, "error": str(e),
        })


# ── App lifecycle ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    start_scheduler()
    sync_jobs(cfg.get("folders", []), _run_organize_job)
    log.info("File Organizer started")
    yield
    stop_scheduler()
    log.info("File Organizer stopped")

app = FastAPI(title="File Organizer", lifespan=lifespan)

# ── Static files ─────────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── HTML page ────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ── WebSocket ────────────────────────────────────────────────────────────

@app.websocket("/ws/progress")
async def ws_progress(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── Folder endpoints ─────────────────────────────────────────────────────

@app.get("/api/folders")
async def list_folders():
    cfg = load_config()
    folders = cfg.get("folders", [])
    # Enrich with next_run
    for f in folders:
        f["next_run"] = get_next_run(f["id"])
    return folders


class FolderCreate(BaseModel):
    path: str
    schedule: str = ""
    enabled: bool = True


@app.post("/api/folders")
async def add_folder(body: FolderCreate):
    if not Path(body.path).is_dir():
        raise HTTPException(400, f"Not a directory: {body.path}")
    cfg = load_config()
    folder = make_folder(body.path, schedule=body.schedule, enabled=body.enabled)
    cfg["folders"].append(folder)
    save_config(cfg)
    sync_jobs(cfg["folders"], _run_organize_job)
    return folder


@app.delete("/api/folders/{folder_id}")
async def remove_folder(folder_id: str):
    cfg = load_config()
    cfg["folders"] = [f for f in cfg["folders"] if f["id"] != folder_id]
    save_config(cfg)
    sync_jobs(cfg["folders"], _run_organize_job)
    return {"ok": True}


# ── Organize trigger ─────────────────────────────────────────────────────

@app.post("/api/organize/{folder_id}")
async def trigger_organize(folder_id: str):
    cfg = load_config()
    folder = next((f for f in cfg["folders"] if f["id"] == folder_id), None)
    if not folder:
        raise HTTPException(404, "Folder not found")
    asyncio.create_task(_run_organize_job(folder_id, folder["path"]))
    return {"status": "started", "folder_id": folder_id}


# ── Preview / dry run ────────────────────────────────────────────────────

@app.post("/api/preview/{folder_id}")
async def preview_organize(folder_id: str):
    cfg = load_config()
    folder = next((f for f in cfg["folders"] if f["id"] == folder_id), None)
    if not folder:
        raise HTTPException(404, "Folder not found")

    settings = cfg.get("settings", {})
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: organize_folder(folder["path"], settings=settings, dry_run=True)
    )
    ops = getattr(result, "_planned_ops", [])
    return {"result": result.to_dict(), "operations": ops}


# ── Settings ─────────────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    cfg = load_config()
    return cfg.get("settings", DEFAULT_SETTINGS)


class SettingsUpdate(BaseModel):
    settings: dict


@app.put("/api/settings")
async def update_settings(body: SettingsUpdate):
    cfg = load_config()
    cfg["settings"].update(body.settings)
    save_config(cfg)
    return cfg["settings"]


# ── Logs ─────────────────────────────────────────────────────────────────

@app.get("/api/logs")
async def get_logs(limit: int = 20):
    log_data = load_run_log()
    return log_data[:limit]


@app.get("/api/logs/{job_id}")
async def get_log_detail(job_id: str):
    log_data = load_run_log()
    entry = next((e for e in log_data if e.get("job_id") == job_id), None)
    if not entry:
        raise HTTPException(404, "Log entry not found")
    return entry


# ── Run ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
