from typing import Literal, Optional
from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    source: Literal["google_maps", "justdial"]
    keyword: str = Field(..., min_length=2)
    city: str = Field(..., min_length=2)
    max_results: int = Field(default=20, ge=1, le=500)
    max_time: int = Field(default=240, ge=30, le=3600)
    headless: Optional[bool] = True


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    message: str