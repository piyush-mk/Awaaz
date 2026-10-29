"""Khata / udhaar (Phase 1, Agent B).

GET  /api/khata/customers, /api/khata/customers/{id}   balances via Customer.balance
POST /api/khata/entries                                add credit or payment (confirm first)
POST /api/khata/import-photo                           khata notebook page -> proposed customers
POST /api/khata/postpaid/{customer_id}                 simulated Paytm Postpaid flow
Customer matching: services.catalog.match_customer. Vision: services.vision (task='khata_page').
"""
from fastapi import APIRouter

from routers._stub import not_implemented

router = APIRouter()


@router.get("/customers")
def list_customers():
    not_implemented("GET /api/khata/customers", "Agent B")


@router.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    not_implemented("GET /api/khata/customers/{id}", "Agent B")


@router.post("/entries")
def add_entry():
    not_implemented("POST /api/khata/entries", "Agent B")


@router.post("/import-photo")
async def import_photo():
    not_implemented("POST /api/khata/import-photo", "Agent B")


@router.post("/postpaid/{customer_id}")
def postpaid(customer_id: int):
    not_implemented("POST /api/khata/postpaid/{customer_id}", "Agent B")
