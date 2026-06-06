from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class ParsedItem(BaseModel):
    product_id: Optional[int] = None
    name: str
    name_hi: str
    quantity: int
    unit: str
    price: float
    gst_rate: float = 0.0


class BillItem(BaseModel):
    product_id: Optional[int] = None
    name: str
    name_hi: str
    quantity: int
    unit: str
    unit_price: float
    subtotal: float
    gst_rate: float
    gst_amount: float
    total: float


class Bill(BaseModel):
    items: List[BillItem]
    subtotal: float
    total_gst: float
    grand_total: float
    upi_string: str


class RestockRequest(BaseModel):
    items: List[ParsedItem]


class BillConfirmRequest(BaseModel):
    items: List[BillItem]
    grand_total: float


class InventoryItem(BaseModel):
    product_id: int
    name: str
    name_hi: str
    category: str
    unit: str
    price: float
    gst_rate: float
    quantity: int
    threshold: int
    status: str  # "high", "medium", "low"

    class Config:
        from_attributes = True


class TransactionOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_name_hi: str
    quantity_change: int
    type: str
    amount: float
    timestamp: datetime

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    total_stock_value: float
    today_sales: float
    low_stock_count: int
    top_selling: List[dict]
    recent_transactions: List[TransactionOut]


class VoiceParseResponse(BaseModel):
    transcript: str
    items: List[ParsedItem]
    demo_mode: bool


class TTSRequest(BaseModel):
    text: str
    language: Optional[str] = 'hi'  # 'hi' or 'en'


class TTSResponse(BaseModel):
    audio_base64: str
    text: str
