from pathlib import Path
from threading import Thread
from datetime import datetime

from app.config import OUTPUTS_DIR
from app.services.job_manager import update_job
from app.scrapers.justdial.scraper import run_justdial_scraper
from app.scrapers.google_maps.scraper import run_google_maps_scraper


def run_scrape_job(job_id: str, source: str, payload: dict):
    def _run():
        try:
            update_job(
                job_id,
                status="running",
                message="Scraper started",
                processed=0,
                total=0,
            )

            def progress_callback(processed: int, total: int, message: str | None = None):
                update_payload = {
                    "status": "running",
                    "processed": processed,
                    "total": total,
                }
                if message:
                    update_payload["message"] = message
                update_job(job_id, **update_payload)

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            output_file = OUTPUTS_DIR / f"{source}_{timestamp}_{job_id}.csv"

            if source == "justdial":
                total_rows = run_justdial_scraper(
                    keyword=payload["keyword"],
                    city=payload["city"],
                    max_results=payload["max_results"],
                    max_time=payload["max_time"],
                    headless=payload["headless"],
                    output_file=output_file,
                    progress_callback=progress_callback,
                )
            elif source == "google_maps":
                total_rows = run_google_maps_scraper(
                    keyword=payload["keyword"],
                    city=payload["city"],
                    max_results=payload["max_results"],
                    max_time=payload["max_time"],
                    headless=payload["headless"],
                    output_file=output_file,
                    progress_callback=progress_callback,
                )
            else:
                raise ValueError("Unsupported source")

            job = update_job(
                job_id,
                status="completed",
                message="Scraper completed successfully",
                total_rows=total_rows,
                output_file=str(output_file.name),
            )

            final_total = int(job.get("total", 0) or 0)
            if final_total > 0:
                update_job(
                    job_id,
                    processed=final_total,
                    total=final_total,
                )

        except Exception as e:
            update_job(
                job_id,
                status="failed",
                message="Scraper failed",
                error=str(e),
            )

    thread = Thread(target=_run, daemon=True)
    thread.start()