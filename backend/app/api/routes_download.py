from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.services.job_manager import get_job
from app.config import OUTPUTS_DIR

router = APIRouter(tags=["download"])


@router.get("/download/{job_id}")
def download_output(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output_file = job.get("output_file")
    if not output_file:
        raise HTTPException(status_code=404, detail="Output file not available")

    file_path = OUTPUTS_DIR / output_file
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(file_path),
        filename=output_file,
        media_type="text/csv",
    )