from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes_health import router as health_router
from app.api.routes_scrape import router as scrape_router
from app.api.routes_download import router as download_router

app = FastAPI(title="Vendor Scraper Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(scrape_router, prefix="/api")
app.include_router(download_router, prefix="/api")