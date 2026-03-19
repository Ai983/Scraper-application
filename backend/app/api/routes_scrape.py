from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.schemas.scrape import ScrapeRequest, JobCreateResponse
from app.schemas.result import JobStatusResponse, JobPreviewResponse
from app.services.job_manager import create_job, get_job
from app.services.scrape_runner import run_scrape_job
from app.services.preview_service import read_preview_rows
from app.config import OUTPUTS_DIR, settings

router = APIRouter(tags=["scrape"])


@router.post("/scrape", response_model=JobCreateResponse)
def start_scrape(payload: ScrapeRequest):
    job_id = datetime.utcnow().strftime("job_%Y%m%d_%H%M%S_%f")
    body = payload.model_dump()
    create_job(job_id=job_id, source=payload.source, payload=body)
    run_scrape_job(job_id=job_id, source=payload.source, payload=body)
    return JobCreateResponse(job_id=job_id, status="running", message="Scraper started")


@router.get("/scrape/{job_id}", response_model=JobStatusResponse)
def get_scrape_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    download_url = None
    if job.get("output_file"):
        download_url = f"/api/download/{job_id}"

    return JobStatusResponse(
        job_id=job["job_id"],
        source=job["source"],
        status=job["status"],
        message=job["message"],
        total_rows=job.get("total_rows", 0),
        output_file=job.get("output_file"),
        download_url=download_url,
        error=job.get("error"),
    )


@router.get("/scrape/{job_id}/preview", response_model=JobPreviewResponse)
def get_scrape_preview(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    rows = []
    if job.get("output_file"):
        rows = read_preview_rows(OUTPUTS_DIR / job["output_file"], limit=settings.preview_rows)

    return JobPreviewResponse(
        job_id=job["job_id"],
        source=job["source"],
        status=job["status"],
        rows=rows,
    )