"""APScheduler-based cron scheduling for recurring organize jobs."""
import datetime
import logging
from typing import Optional, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger("scheduler")

_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def start_scheduler() -> None:
    s = get_scheduler()
    if not s.running:
        s.start()
        log.info("Scheduler started")


def stop_scheduler() -> None:
    s = get_scheduler()
    if s.running:
        s.shutdown(wait=False)
        log.info("Scheduler stopped")


def sync_jobs(folders: list, run_func: Callable) -> None:
    """Sync scheduled jobs to match current folder config.

    Args:
        folders: List of folder config dicts with id, path, schedule, enabled.
        run_func: Async callable(folder_id, folder_path) to execute on trigger.
    """
    s = get_scheduler()

    # Remove jobs that no longer exist or are disabled
    existing_ids = {f"organize_{f['id']}" for f in folders if f.get("enabled") and f.get("schedule")}
    for job in s.get_jobs():
        if job.id.startswith("organize_") and job.id not in existing_ids:
            s.remove_job(job.id)
            log.info(f"Removed job {job.id}")

    # Add or update jobs
    for folder in folders:
        job_id = f"organize_{folder['id']}"
        schedule = folder.get("schedule", "")
        enabled = folder.get("enabled", True)

        if not schedule or not enabled:
            # Remove if exists
            try:
                s.remove_job(job_id)
            except Exception:
                pass
            continue

        try:
            trigger = CronTrigger.from_crontab(schedule)
        except Exception as e:
            log.warning(f"Invalid cron for {folder['id']}: {schedule} ({e})")
            continue

        # Replace or add
        try:
            s.remove_job(job_id)
        except Exception:
            pass

        s.add_job(
            run_func,
            trigger=trigger,
            id=job_id,
            args=[folder["id"], folder["path"]],
            name=f"Organize {folder.get('path', folder['id'])}",
            misfire_grace_time=300,
        )
        log.info(f"Scheduled {job_id}: {schedule}")


def get_next_run(folder_id: str) -> Optional[str]:
    """Get next scheduled run time for a folder, or None."""
    s = get_scheduler()
    try:
        job = s.get_job(f"organize_{folder_id}")
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
    except Exception:
        pass
    return None
