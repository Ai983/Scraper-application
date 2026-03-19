from typing import Any, List, Optional
from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    job_id: str
    source: str
    status: str
    message: str
    total_rows: int = 0
    output_file: Optional[str] = None
    download_url: Optional[str] = None
    error: Optional[str] = None


class JobPreviewResponse(BaseModel):
    job_id: str
    source: str
    status: str
    rows: List[dict[str, Any]]