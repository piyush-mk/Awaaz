"""Run once to initialize the database with products, inventory, and demo data."""
from database import engine, SessionLocal
from models import Base, Product, Inventory, Transaction, Customer
from datetime import datetime, timedelta
import random

Base.metadata.create_all(bind=engine)

PRODUCTS = [
    {"id": 1, "name": "Maggi", "name_hi": "मैगी", "category": "food", "unit": "packet", "price": 12.0, "gst_rate": 12.0, "threshold": 5},
    {"id": 2, "name": "Rice 5kg", "name_hi": "चावल", "category": "staples", "unit": "bag", "price": 350.0, "gst_rate": 0.0, "threshold": 3},
    {"id": 3, "name": "Surf Excel", "name_hi": "सर्फ एक्सेल", "category": "cleaning", "unit": "packet", "price": 45.0, "gst_rate": 18.0, "threshold": 5},
    {"id": 4, "name": "Tata Salt", "name_hi": "टाटा नमक", "category": "staples", "unit": "packet", "price": 28.0, "gst_rate": 0.0, "threshold": 5},
    {"id": 5, "name": "Colgate", "name_hi": "कोलगेट", "category": "personal_care", "unit": "packet", "price": 45.0, "gst_rate": 12.0, "threshold": 4},
    {"id": 6, "name": "Aashirvaad Atta 5kg", "name_hi": "आशीर्वाद आटा", "category": "staples", "unit": "bag", "price": 320.0, "gst_rate": 0.0, "threshold": 3},
    {"id": 7, "name": "Patanjali Honey", "name_hi": "पतंजलि शहद", "category": "food", "unit": "bottle", "price": 180.0, "gst_rate": 12.0, "threshold": 3},
    {"id": 8, "name": "Vim Bar", "name_hi": "विम बार", "category": "cleaning", "unit": "bar", "price": 15.0, "gst_rate": 18.0, "threshold": 5},
    {"id": 9, "name": "Parle-G", "name_hi": "पारले-जी", "category": "food", "unit": "packet", "price": 10.0, "gst_rate": 12.0, "threshold": 8},
    {"id": 10, "name": "Dettol Soap", "name_hi": "डेटॉल साबुन", "category": "personal_care", "unit": "soap", "price": 35.0, "gst_rate": 18.0, "threshold": 4},
]

# Mix of high/medium/low for demo alerts (Salt, Atta, Vim are LOW)
INITIAL_STOCK = {
    1: 12,   # Maggi - medium
    2: 8,    # Rice - medium
    3: 15,   # Surf Excel - high
    4: 3,    # Tata Salt - LOW (below threshold 5)
    5: 10,   # Colgate - medium
    6: 2,    # Aashirvaad Atta - LOW (below threshold 3)
    7: 7,    # Patanjali Honey - medium
    8: 4,    # Vim Bar - LOW (below threshold 5)
    9: 20,   # Parle-G - high
    10: 6,   # Dettol Soap - medium
}

def seed():
    db = SessionLocal()
    try:
        if db.query(Product).count() > 0:
            print("Database already seeded. Skipping.")
            return

        # Seed products
        for p in PRODUCTS:
            db.add(Product(**p))
        db.flush()

        # Seed inventory
        for product_id, qty in INITIAL_STOCK.items():
            db.add(Inventory(product_id=product_id, quantity=qty))
        db.flush()

        # Seed mock transactions for analytics
        now = datetime.utcnow()
        mock_transactions = [
            # Today
            Transaction(product_id=1, quantity_change=-3, type="sale", amount=36.0, timestamp=now - timedelta(hours=2)),
            Transaction(product_id=5, quantity_change=-2, type="sale", amount=90.0, timestamp=now - timedelta(hours=3)),
            Transaction(product_id=3, quantity_change=-1, type="sale", amount=45.0, timestamp=now - timedelta(hours=4)),
            # Yesterday
            Transaction(product_id=9, quantity_change=-5, type="sale", amount=50.0, timestamp=now - timedelta(days=1, hours=1)),
            Transaction(product_id=1, quantity_change=-4, type="sale", amount=48.0, timestamp=now - timedelta(days=1, hours=3)),
            Transaction(product_id=10, quantity_change=-2, type="sale", amount=70.0, timestamp=now - timedelta(days=1, hours=5)),
            # 2 days ago
            Transaction(product_id=2, quantity_change=-1, type="sale", amount=350.0, timestamp=now - timedelta(days=2, hours=2)),
            Transaction(product_id=4, quantity_change=-2, type="sale", amount=56.0, timestamp=now - timedelta(days=2, hours=4)),
            Transaction(product_id=8, quantity_change=-3, type="sale", amount=45.0, timestamp=now - timedelta(days=2, hours=6)),
            # Restock
            Transaction(product_id=1, quantity_change=24, type="restock", amount=0, timestamp=now - timedelta(days=3)),
            Transaction(product_id=9, quantity_change=50, type="restock", amount=0, timestamp=now - timedelta(days=3)),
        ]
        for t in mock_transactions:
            db.add(t)

        # Seed a demo customer
        db.add(Customer(name="Walk-in Customer", phone=None, visit_count=0, total_spent=0))

        db.commit()
        print("✅ Database seeded successfully!")
        print(f"   Products: {len(PRODUCTS)}")
        print(f"   Low stock alerts: Tata Salt (3), Aashirvaad Atta (2), Vim Bar (4)")
        print(f"   Mock transactions: {len(mock_transactions)}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
