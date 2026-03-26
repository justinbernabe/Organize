"""Settings model and JSON persistence for the file organizer."""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from organizer import DEFAULT_CATEGORIES, DEFAULT_FOLDER_MAPPINGS

# ── Default config path ──────────────────────────────────────────────────

DEFAULT_CONFIG_DIR = Path(os.environ.get(
    "FILE_ORGANIZER_CONFIG", os.path.expanduser("~/.config/file-organizer")
))
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"


# ── Default settings ─────────────────────────────────────────────────────

DEFAULT_SETTINGS: Dict[str, Any] = {
    "default_action": "organize",       # "organize" | "timestamps_only"
    "dry_run": False,
    "set_modified_date": True,
    "enable_file_moving": True,
    "name_scheme": "lowercase",          # "lowercase" | "UPPERCASE" | "Title Case"
    "categories": DEFAULT_CATEGORIES,
    "folder_mappings": DEFAULT_FOLDER_MAPPINGS,
    "enable_duplicates": False,
    "hash_threshold_mb": 100,
    "duplicate_policy": "keep_oldest",
}


# ── Folder entry ─────────────────────────────────────────────────────────

def make_folder(path: str, folder_id: Optional[str] = None,
                schedule: str = "", enabled: bool = True) -> dict:
    """Create a folder config entry."""
    import uuid
    return {
        "id": folder_id or uuid.uuid4().hex[:8],
        "path": path,
        "schedule": schedule,   # cron expression, empty = manual only
        "enabled": enabled,
    }


# ── Config load / save ───────────────────────────────────────────────────

def _default_config() -> dict:
    return {
        "folders": [],
        "settings": dict(DEFAULT_SETTINGS),
    }


def load_config(path: Optional[Path] = None) -> dict:
    """Load config from JSON, returning defaults if missing or corrupt."""
    p = path or DEFAULT_CONFIG_FILE
    if p.exists():
        try:
            with open(p, "r") as f:
                data = json.load(f)
            # Merge with defaults so new keys get filled in
            cfg = _default_config()
            cfg["folders"] = data.get("folders", [])
            saved = data.get("settings", {})
            for k, v in DEFAULT_SETTINGS.items():
                cfg["settings"][k] = saved.get(k, v)
            return cfg
        except Exception:
            pass
    return _default_config()


def save_config(cfg: dict, path: Optional[Path] = None) -> None:
    """Persist config to JSON. Creates parent dirs if needed."""
    p = path or DEFAULT_CONFIG_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Run log persistence ──────────────────────────────────────────────────

DEFAULT_LOG_FILE = DEFAULT_CONFIG_DIR / "run_log.json"
MAX_LOG_ENTRIES = 100


def load_run_log(path: Optional[Path] = None) -> List[dict]:
    """Load recent run log entries."""
    p = path or DEFAULT_LOG_FILE
    if p.exists():
        try:
            with open(p, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def append_run_log(entry: dict, path: Optional[Path] = None) -> None:
    """Append a run log entry, trimming to MAX_LOG_ENTRIES."""
    p = path or DEFAULT_LOG_FILE
    log = load_run_log(p)
    log.insert(0, entry)
    log = log[:MAX_LOG_ENTRIES]
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(log, f, indent=2)
