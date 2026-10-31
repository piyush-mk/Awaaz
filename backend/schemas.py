"""Pydantic models.

Two groups:
  * legacy request/response models used by /api/voice, /api/photo, /api/inventory,
    /api/bill and /api/dashboard (shapes unchanged, quantities are now floats);
  * v2 shared contracts (CartLine, Cart, PendingActionOut, AIResult, Invoice/
    Payment/Khata outs) that Phase 1 routers code against.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# v2 shared contracts
# ---------------------------------------------------------------------------

AISource = Literal["sarvam", "openrouter", "rules", "fixture"]


class AIResult(BaseModel):
    """Envelope for any AI-produced payload; the UI renders source/latency as a chip."""

    data: Any = None
    source: AISource = "rules"
    latency_ms: int = 0


class CartLine(BaseModel):
    """One line of a counter cart. `unit_price` is MRP-inclusive per `unit`."""

    product_id: Optional[int] = None
    name: str
    name_hi: str = ""
    qty: float
    unit: str = ""  # display unit: packet, kg, litre...
    sell_mode: Literal["unit", "loose"] = "unit"
    base_unit: str = "pc"
    unit_price: float = 0.0
    line_total: float = 0.0
    gst_rate: float = 0.0
    amount_rupees: Optional[float] = None  # set when the customer asked "Rs N ka X"
    weigh_instruction: Optional[str] = None  # e.g. "450 gram tolo"
    flags: List[str] = Field(default_factory=list)
    raw: str = ""  # the spoken words that produced this line
    confidence: float = 1.0


class Cart(BaseModel):
    id: str
    lines: List[CartLine] = Field(default_factory=list)
    customer_id: Optional[int] = None
    status: Literal["open", "checked_out", "cancelled"] = "open"
    invoice_id: Optional[int] = None
    total: float = 0.0
    taxable_total: float = 0.0
    cgst_total: float = 0.0
    sgst_total: float = 0.0
    updated_at: Optional[datetime] = None


class PendingActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    payload: dict = Field(default_factory=dict)
    status: Literal["proposed", "confirmed", "cancelled"] = "proposed"
    source: Optional[str] = None
    latency_ms: Optional[int] = None
    session_id: Optional[str] = None
    result: Optional[dict] = None
    created_at: Optional[datetime] = None


class InvoiceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: Optional[int] = None
    name: str
    name_hi: str = ""
    qty: float
    unit: str = ""
    mrp: float
    gst_rate: float
    hsn: Optional[str] = None
    taxable: float
    cgst: float
    sgst: float
    total: float


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: Optional[int] = None
    customer_id: Optional[int] = None
    mode: Literal["upi", "cash", "khata", "postpaid", "card"]
    amount: float
    status: Literal["pending", "success", "failed", "refunded"] = "pending"
    order_id: Optional[str] = None
    rail: str = "simulated"
    created_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    doc_type: Literal["tax_invoice", "bill_of_supply"] = "tax_invoice"
    customer_id: Optional[int] = None
    status: str = "pending"
    taxable_total: float = 0.0
    cgst_total: float = 0.0
    sgst_total: float = 0.0
    total: float = 0.0
    public_token: Optional[str] = None
    created_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    items: List[InvoiceItemOut] = Field(default_factory=list)
    payments: List[PaymentOut] = Field(default_factory=list)


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    name_hi: Optional[str] = None
    phone: Optional[str] = None
    upi_id: Optional[str] = None
    language: str = "hi-IN"
    credit_limit: float = 0.0
    late_payments: int = 0
    balance: float = 0.0  # > 0 means the customer owes the shop


class KhataEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    amount: float  # + credit given, - payment received
    invoice_id: Optional[int] = None
    note: Optional[str] = None
    wa_status: Optional[str] = None
    confirmed_by_customer: bool = False
    at: Optional[datetime] = None


class NotImplementedOut(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# Legacy models (voice / photo / inventory / bill / dashboard)
# ---------------------------------------------------------------------------


class ParsedItem(BaseModel):
    product_id: Optional[int] = None
    name: str
    name_hi: str = ""
    quantity: float
    unit: str
    price: float
    gst_rate: float = 0.0


class BillItem(BaseModel):
    product_id: int
    name: str
    name_hi: str = ""
    quantity: float
    unit: str
    unit_price: float
    subtotal: float  # taxable value (MRP-inclusive pricing)
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
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    name: str
    name_hi: str
    category: str
    unit: str
    price: float
    gst_rate: float
    quantity: float
    threshold: float
    status: str  # "high", "medium", "low"


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    product_name_hi: str
    quantity_change: float
    type: str
    amount: float
    timestamp: datetime


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
    source: Optional[AISource] = None
    latency_ms: Optional[int] = None


class TTSRequest(BaseModel):
    text: str
    language: str = "hi-IN"
    speaker: Optional[str] = None


class TTSResponse(BaseModel):
    audio_base64: str
    text: str
    url: Optional[str] = None
    source: Optional[AISource] = None
