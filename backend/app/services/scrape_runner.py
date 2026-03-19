from pathlib import Path
from threading import Thread
from datetime import datetime
import traceback

from app.config import OUTPUTS_DIR
from app.services.job_manager import update_job
from app.scrapers.justdial.scraper import run_justdial_scraper
from app.scrapers.google_maps.scraper import run_google_maps_scraper


def run_scrape_job(job_id: str, source: str, payload: dict):
    def _run():
        try:
            print(f"[JOB {job_id}] Starting scrape job")
            print(f"[JOB {job_id}] Source: {source}")
            print(f"[JOB {job_id}] Payload: {payload}")

            update_job(
                job_id,
                status="running",
                message="Scraper started",
                processed=0,
                total=0,
            )

            def progress_callback(processed: int, total: int, message: str | None = None):
                print(
                    f"[JOB {job_id}] Progress update -> processed={processed}, total={total}, message={message}"
                )
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
            print(f"[JOB {job_id}] Output file: {output_file}")

            if source == "justdial":
                print(f"[JOB {job_id}] Running Justdial scraper")
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
                print(f"[JOB {job_id}] Running Google Maps scraper")
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

            print(f"[JOB {job_id}] Scraper finished with total_rows={total_rows}")

            job = update_job(
                job_id,
                status="completed",
                message="Scraper completed successfully",
                total_rows=total_rows,
                output_file=str(output_file.name),
            )

            final_total = int(job.get("total", 0) or 0)
            if final_total > 0:
                print(f"[JOB {job_id}] Finalizing totals -> {final_total}")
                update_job(
                    job_id,
                    processed=final_total,
                    total=final_total,
                )

            print(f"[JOB {job_id}] Completed successfully")

        except Exception as e:
            error_trace = traceback.format_exc()
            print(f"[JOB {job_id}] FAILED")
            print(error_trace)

            update_job(
                job_id,
                status="failed",
                message=f"Scraper failed: {str(e)}",
                error=error_trace,
            )

    thread = Thread(target=_run, daemon=True)
    thread.start()