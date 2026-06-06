from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine
from models import Base
from routers import voice, inventory, billing, dashboard

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Paytm Voice Business Suite", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice.router, prefix="/api/voice", tags=["Voice AI"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(billing.router, prefix="/api/bill", tags=["Billing"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])


@app.get("/")
def root():
    return {"status": "ok", "app": "Paytm Voice Business Suite"}


@app.get("/health")
def health():
    return {"status": "healthy"}
