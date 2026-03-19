from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
JOBS_DIR = STORAGE_DIR / "jobs"
OUTPUTS_DIR = STORAGE_DIR / "outputs"
TEMP_DIR = STORAGE_DIR / "temp"

for folder in [STORAGE_DIR, JOBS_DIR, OUTPUTS_DIR, TEMP_DIR]:
    folder.mkdir(parents=True, exist_ok=True)


class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    headless: bool = os.getenv("HEADLESS", "true").lower() == "true"
    preview_rows: int = int(os.getenv("PREVIEW_ROWS", "50"))
    default_max_results: int = int(os.getenv("DEFAULT_MAX_RESULTS", "20"))
    default_max_time: int = int(os.getenv("DEFAULT_MAX_TIME", "240"))


settings = Settings()