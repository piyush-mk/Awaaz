"""Awaaz v2 data model.

Quantities are Float everywhere (loose goods are sold by weight/volume).
Money is stored as Float rupees rounded to 2 places; all GST arithmetic is done
in integer paise by `services/pricing.py` before values reach these columns.
Datetimes are naive store-local (IST), see `services/clock.py`.

Legacy compatibility: the old `Inventory` and `Transaction` tables are gone.
Stock is the sum of `StockBatch.qty`; the legacy "transaction" feed is derived
from `StockMove` (see routers/dashboard.py).
"""
from __future__ import annotations

from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, func, select,
)
from sqlalchemy.orm import column_property, relationship

from database import Base
from services.clock import now_local


class StoreProfile(Base):
    __tablename__ = "store_profile"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    owner_name = Column(String, default="")
    address = Column(String, default="")
    phone = Column(String, nullable=True)
    upi_vpa = Column(String, default="")
    gstin = Column(String, nullable=True)
    composition_scheme = Column(Boolean, default=False)
    language = Column(String, default="hi-IN")
    opening_float = Column(Float, default=0.0)
    invoice_prefix = Column(String, default="INV")


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    contact_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    gstin = Column(String, nullable=True)
    visit_day = Column(String, nullable=True)  # e.g. "Saturday"
    lead_days = Column(Integer, default=1)
    notes = Column(String, default="")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    name_hi = Column(String, nullable=False, default="")
    aliases = Column(JSON, default=list)  # spoken names, romanised and Devanagari
    category = Column(String, default="general")
    hsn = Column(String, nullable=True)
    gst_rate = Column(Float, default=0.0)  # percent, MRP-inclusive
    mrp = Column(Float, nullable=False, default=0.0)  # per sell unit (per base unit if loose)
    cost_price = Column(Float, nullable=True)
    sell_mode = Column(String, default="unit")  # "unit" | "loose"
    base_unit = Column(String, default="pc")  # "pc" | "kg" | "l"
    unit = Column(String, default="packet")  # display unit: packet, bag, kg, litre...
    loose_price_per_base = Column(Float, nullable=True)  # Rs per kg / litre when loose
    pack_size = Column(Float, nullable=True)  # children per pack (pack-breaking)
    parent_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    barcode = Column(String, nullable=True)
    threshold = Column(Float, default=5)
    festival_tags = Column(JSON, default=list)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    active = Column(Boolean, default=True)

    batches = relationship("StockBatch", back_populates="product", cascade="all, delete-orphan")
    supplier = relationship("Supplier")

    @property
    def price(self) -> float:
        """Customer price per sell unit (legacy name). Loose goods: Rs per base unit."""
        if self.sell_mode == "loose" and self.loose_price_per_base is not None:
            return float(self.loose_price_per_base)
        return float(self.mrp or 0.0)

    @property
    def is_loose(self) -> bool:
        return self.sell_mode == "loose"


class StockBatch(Base):
    __tablename__ = "stock_batches"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True, nullable=False)
    qty = Column(Float, nullable=False, default=0.0)
    batch_no = Column(String, nullable=True)
    expiry = Column(Date, nullable=True)
    cost_price = Column(Float, nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    received_at = Column(DateTime, default=now_local)

    product = relationship("Product", back_populates="batches")


class StockMove(Base):
    """Append-only stock ledger. `amount` is the money value of the move (sale total)."""

    __tablename__ = "stock_moves"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True, nullable=False)
    qty_change = Column(Float, nullable=False)
    kind = Column(String, nullable=False)  # sale|restock|adjust|audit|return
    ref = Column(String, nullable=True)  # "invoice:12", "purchase:3"
    amount = Column(Float, default=0.0)
    note = Column(String, nullable=True)
    at = Column(DateTime, default=now_local, index=True)

    product = relationship("Product")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, default="Walk-in Customer")
    name_hi = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    upi_id = Column(String, nullable=True)
    language = Column(String, default="hi-IN")
    credit_limit = Column(Float, default=1000.0)
    late_payments = Column(Integer, default=0)
    usual_basket = Column(JSON, default=list)  # [{"product_id": 1, "qty": 2}]
    notes = Column(String, default="")
    created_at = Column(DateTime, default=now_local)


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    number = Column(String, unique=True, index=True, nullable=False)
    doc_type = Column(String, default="tax_invoice")  # tax_invoice | bill_of_supply
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    status = Column(String, default="pending")  # pending | paid | cancelled
    taxable_total = Column(Float, default=0.0)
    cgst_total = Column(Float, default=0.0)
    sgst_total = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    public_token = Column(String, unique=True, index=True, nullable=True)
    cart_id = Column(String, nullable=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=now_local, index=True)
    paid_at = Column(DateTime, nullable=True)

    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")
    customer = relationship("Customer")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), index=True, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), index=True, nullable=True)
    name = Column(String, nullable=False)
    name_hi = Column(String, default="")
    qty = Column(Float, nullable=False)
    unit = Column(String, default="")
    mrp = Column(Float, default=0.0)  # unit price, GST-inclusive
    gst_rate = Column(Float, default=0.0)
    hsn = Column(String, nullable=True)
    taxable = Column(Float, default=0.0)
    cgst = Column(Float, default=0.0)
    sgst = Column(Float, default=0.0)
    total = Column(Float, default=0.0)

    invoice = relationship("Invoice", back_populates="items")
    product = relationship("Product")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), index=True, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    mode = Column(String, nullable=False)  # upi|cash|khata|postpaid|card
    amount = Column(Float, nullable=False)
    status = Column(String, default="pending")  # pending|success|failed|refunded
    order_id = Column(String, unique=True, index=True, nullable=True)
    rail = Column(String, default="simulated")  # upi_intent|paytm_dqr|simulated
    created_at = Column(DateTime, default=now_local, index=True)
    paid_at = Column(DateTime, nullable=True)

    invoice = relationship("Invoice", back_populates="payments")


class KhataEntry(Base):
    """Ledger line: amount > 0 is credit given (udhaar), amount < 0 is a payment received."""

    __tablename__ = "khata_entries"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True, nullable=False)
    amount = Column(Float, nullable=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    note = Column(String, nullable=True)
    wa_status = Column(String, nullable=True)  # queued|sent|delivered|failed
    confirmed_by_customer = Column(Boolean, default=False)
    at = Column(DateTime, default=now_local, index=True)

    customer = relationship("Customer", backref="khata_entries")


class PurchaseBill(Base):
    __tablename__ = "purchase_bills"

    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    bill_no = Column(String, nullable=True)
    bill_date = Column(Date, nullable=True)
    total = Column(Float, default=0.0)
    status = Column(String, default="proposed")  # proposed|confirmed|cancelled
    photo_ref = Column(String, nullable=True)
    flags = Column(JSON, default=list)
    created_at = Column(DateTime, default=now_local)

    supplier = relationship("Supplier")
    items = relationship("PurchaseItem", back_populates="bill", cascade="all, delete-orphan")


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True)
    bill_id = Column(Integer, ForeignKey("purchase_bills.id"), index=True, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), index=True, nullable=True)
    name_raw = Column(String, nullable=False)
    qty = Column(Float, default=0.0)
    unit = Column(String, nullable=True)
    rate = Column(Float, default=0.0)  # per-unit cost on the bill
    prev_rate = Column(Float, nullable=True)  # last cost from an earlier bill
    mrp = Column(Float, nullable=True)
    batch_no = Column(String, nullable=True)
    expiry = Column(Date, nullable=True)
    scheme_text = Column(String, nullable=True)
    free_qty_expected = Column(Float, default=0.0)
    free_qty_received = Column(Float, default=0.0)
    flags = Column(JSON, default=list)

    bill = relationship("PurchaseBill", back_populates="items")
    product = relationship("Product")


class MissedSale(Base):
    __tablename__ = "missed_sales"

    id = Column(Integer, primary_key=True)
    product_name = Column(String, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    at = Column(DateTime, default=now_local, index=True)


class CashClosing(Base):
    __tablename__ = "cash_closings"

    id = Column(Integer, primary_key=True)
    day = Column(Date, nullable=False)
    expected = Column(Float, default=0.0)
    counted = Column(Float, default=0.0)
    denominations = Column(JSON, default=dict)
    diff = Column(Float, default=0.0)  # counted - expected
    photo_ref = Column(String, nullable=True)
    created_at = Column(DateTime, default=now_local)


class PendingAction(Base):
    """Propose -> confirm -> commit. `payload` holds the structured diff."""

    __tablename__ = "pending_actions"

    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False)  # add_udhaar, restock, purchase_bill, ...
    payload = Column(JSON, default=dict)
    status = Column(String, default="proposed")  # proposed|confirmed|cancelled
    source = Column(String, nullable=True)  # sarvam|openrouter|rules|fixture
    latency_ms = Column(Integer, nullable=True)
    session_id = Column(String, nullable=True)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=now_local)
    resolved_at = Column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    channel = Column(String, default="sim")  # wa|sim
    to = Column(String, nullable=True)
    sender = Column(String, nullable=True)
    direction = Column(String, default="out")  # in|out
    type = Column(String, default="text")  # text|audio|image|doc
    body = Column(Text, nullable=True)
    media_ref = Column(String, nullable=True)
    wa_id = Column(String, nullable=True)
    status = Column(String, default="queued")
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    created_at = Column(DateTime, default=now_local, index=True)


class Cart(Base):
    """Open counter cart, keyed by session id. `lines` is a list of CartLine dicts."""

    __tablename__ = "carts"

    id = Column(String, primary_key=True)
    lines = Column(JSON, default=list)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    status = Column(String, default="open")  # open|checked_out|cancelled
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    updated_at = Column(DateTime, default=now_local, onupdate=now_local)


# Customer.balance: sum of KhataEntry.amount (positive = customer owes the shop).
Customer.balance = column_property(
    select(func.coalesce(func.sum(KhataEntry.amount), 0.0))
    .where(KhataEntry.customer_id == Customer.id)
    .correlate_except(KhataEntry)
    .scalar_subquery()
)
