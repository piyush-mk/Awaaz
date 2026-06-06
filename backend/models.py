from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    name_hi = Column(String, nullable=False)
    category = Column(String, default="general")
    unit = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    gst_rate = Column(Float, default=0.0)
    threshold = Column(Integer, default=5)

    inventory = relationship("Inventory", back_populates="product", uselist=False)
    transactions = relationship("Transaction", back_populates="product")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), unique=True)
    quantity = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="inventory")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity_change = Column(Integer, nullable=False)
    type = Column(String, nullable=False)  # "sale" or "restock"
    amount = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="transactions")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Walk-in Customer")
    phone = Column(String, nullable=True)
    last_visit = Column(DateTime, default=datetime.utcnow)
    total_spent = Column(Float, default=0.0)
    visit_count = Column(Integer, default=0)
