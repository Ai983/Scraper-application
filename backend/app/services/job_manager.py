from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import JOBS_DIR
from app.utils.files import write_json, read_json


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _calculate_progress_percent(processed: int, total: int) -> int:
    if total <= 0:
        return 0
    percent = int((processed / total) * 100)
    return max(0, min(percent, 100))


def create_job(job_id: str, source: str, payload: dict[str, Any]) -> dict[str, Any]:
    job = {
        "job_id": job_id,
        "source": source,
        "status": "queued",
        "message": "Job created",
        "payload": payload,
        "total_rows": 0,
        "processed": 0,
        "total": 0,
        "progress_percent": 0,
        "output_file": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    write_json(_job_path(job_id), job)
    return job


def update_job(job_id: str, **updates: Any) -> dict[str, Any]:
    path = _job_path(job_id)
    job = read_json(path)

    job.update(updates)

    processed = int(job.get("processed", 0) or 0)
    total = int(job.get("total", 0) or 0)
    job["progress_percent"] = _calculate_progress_percent(processed, total)

    job["updated_at"] = datetime.utcnow().isoformat()
    write_json(path, job)
    return job


def get_job(job_id: str) -> dict[str, Any]:
    return read_json(_job_path(job_id))