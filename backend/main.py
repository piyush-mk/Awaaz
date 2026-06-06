from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from database import engine
from models import Base
from routers import voice, inventory, billing, dashboard, photo

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Paytm Voice Business Suite", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice.router,     prefix="/api/voice",     tags=["Voice AI"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(billing.router,   prefix="/api/bill",      tags=["Billing"])
app.include_router(dashboard.router, prefix="/api",           tags=["Dashboard"])
app.include_router(photo.router,     prefix="/api/photo",     tags=["Photo Inventory"])

STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        return FileResponse(STATIC_DIR / "index.html")
else:
    @app.get("/")
    def root():
        return {"status": "ok", "app": "Paytm Voice Business Suite"}

    @app.get("/health")
    def health():
        return {"status": "healthy"}
