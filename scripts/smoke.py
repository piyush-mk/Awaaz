#!/usr/bin/env python3
"""End-to-end smoke test: plays the deck's story through the HTTP API and asserts the numbers.

    python scripts/smoke.py --base http://localhost:8000            # fixtures / whatever keys the server has
    python scripts/smoke.py --base https://host --live               # real provider calls were configured

It RESETS the demo data first (POST /api/admin/reset-demo), so only point it at a demo server.
Exit code 0 means every check passed.
"""
from __future__ import annotations

import argparse
import base64
import sys
import time
from urllib.parse import urlparse

import httpx

# 1x1 transparent PNG, enough to satisfy an image upload when the server is on fixtures.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    return bool(ok)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--live", action="store_true", help="expect real providers (reports the source chips)")
    args = ap.parse_args()
    c = httpx.Client(base_url=args.base.rstrip("/"), timeout=60.0, follow_redirects=True)
    session = f"smoke-{int(time.time())}"

    def post(path, **kw):
        r = c.post(path, **kw)
        if r.status_code >= 400:
            print(f"    ! {path} -> {r.status_code} {r.text[:200]}")
        return r

    print(f"Smoke test against {args.base}")
    print("0. reset + checklist")
    check("server healthy", c.get("/health").json().get("status") == "healthy")
    check("reset-demo ok", post("/api/admin/reset-demo").status_code == 200)
    cl = c.get("/api/admin/demo-checklist").json()
    check("demo checklist ready", cl.get("ready"), f"{cl.get('passed')}/{cl.get('total')} failed={cl.get('failed')}")

    print("1. distributor bill scan (deck slide 6, 9:30 am)")
    r = post("/api/purchases/scan", files={"image": ("bill.png", PNG, "image/png")})
    scan = r.json() if r.status_code == 200 else {}
    codes = {f["code"] for f in scan.get("flags", [])}
    check("scan returns a proposal", r.status_code == 200 and scan.get("action_id"), f"source={scan.get('source')}")
    check("price guard flags Surf Rs3 costlier", "price_increase" in codes)
    check("scheme guard flags missing free packet", "scheme_missed" in codes)
    surf_before = next((i["qty"] for i in c.get("/api/stock").json()["items"] if i["name"] == "Surf Excel"), None)
    if scan.get("action_id"):
        rc = post(f"/api/purchases/{scan['action_id']}/confirm", json={})
        check("bill confirm updates stock", rc.status_code == 200)
        surf_after = next((i["qty"] for i in c.get("/api/stock").json()["items"] if i["name"] == "Surf Excel"), None)
        check("Surf stock increased", surf_before is not None and surf_after > surf_before, f"{surf_before}->{surf_after}")

    print("2. the counter (slide 5): voice -> cart -> exact QR -> paid -> stock -> receipts")
    colgate_before = next(i["qty"] for i in c.get("/api/stock").json()["items"] if i["name"] == "Colgate")
    u = post("/api/agent/utterance", data={"text": "do maggi ek surf excel chaar colgate", "session_id": session}).json()
    check("cart has 3 lines", len(u.get("cart", {}).get("lines", [])) == 3)
    check("cart total is Rs249 (MRP inclusive)", abs(u.get("cart", {}).get("total", 0) - 249.0) < 0.01, str(u.get("cart", {}).get("total")))
    u2 = post("/api/agent/utterance", data={"text": "bees rupaye ki cheeni", "session_id": session}).json()
    cheeni = [ln for ln in u2.get("cart", {}).get("lines", []) if "cheeni" in (ln.get("name") or "").lower()]
    check("loose sugar line says weigh 450 g", bool(cheeni) and "450" in str(cheeni[0].get("weigh_instruction")), str(cheeni[0].get("weigh_instruction") if cheeni else None))
    # remove sugar again so the demo bill is exactly Rs249
    if cheeni:
        c.delete(f"/api/cart/{session}/lines/{cheeni[0]['product_id']}")
    co = post(f"/api/cart/{session}/checkout", json={}).json()
    check("checkout total Rs249 with UPI intent QR", abs(co.get("total", 0) - 249.0) < 0.01 and str(co.get("upi_string", "")).startswith("upi://pay"), str(co.get("total")))
    check("QR carries the exact amount", "am=249.00" in str(co.get("upi_string")))
    pay = post(f"/api/payments/{co['order_id']}/simulate").json() if co.get("order_id") else {}
    check("payment settles", pay.get("ok") or pay.get("already_paid"))
    check("spoken confirmation", "249" in str(pay.get("spoken_text")), str(pay.get("spoken_text")))
    colgate_after = next(i["qty"] for i in c.get("/api/stock").json()["items"] if i["name"] == "Colgate")
    # The bill-scan fixture in step 1 also restocks Colgate, so assert on the change, not the absolute 12 -> 8.
    check("Colgate stock dropped by 4", colgate_before - colgate_after == 4, f"{colgate_before}->{colgate_after}")
    again = post(f"/api/payments/{co['order_id']}/simulate").json()
    check("second simulate is a no-op", again.get("already_paid") is True)
    token_url = co.get("receipt_url", "")
    # receipt_url is built from PUBLIC_BASE_URL, which may differ from --base: request its path only
    rr = c.get(urlparse(token_url).path) if token_url else None
    check("public receipt page renders", rr is not None and rr.status_code == 200 and "RGS/" in rr.text)

    print("3. udhaar with proof + Postpaid (slide 6, 1:00 pm)")
    ud = post("/api/agent/utterance", data={"text": "verma ji ke khate mein 500", "session_id": session + "u"}).json()
    act = next((a for a in ud.get("actions", []) if a.get("kind") == "add_udhaar"), None)
    check("udhaar proposed as a pending action", bool(act), str([a.get("kind") for a in ud.get("actions", [])]))
    if act:
        post(f"/api/actions/{act['id']}/confirm", json={})
    cust = next((x for x in c.get("/api/khata/customers").json() if "Verma" in x["name"]), {})
    check("Verma ji balance 850 -> 1350", abs(cust.get("balance", 0) - 1350.0) < 0.01, str(cust.get("balance")))
    msgs = c.get("/api/wa/messages", params={"customer_id": cust.get("id", 0)}).json()
    check("WhatsApp confirmation sent", any("1,350" in str(m.get("body")) and "Galat ho toh reply karein" in str(m.get("body")) for m in msgs))
    off = post("/api/khata/postpaid/offer", json={"customer_id": cust.get("id"), "amount": 500}).json()
    check("Postpaid offer is labelled simulated", off.get("simulated") is True and off.get("offer_id"))

    print("4. closing the galla (slide 6, 9:30 pm)")
    g = post("/api/galla/scan", files={"image": ("cash.png", PNG, "image/png")}).json()
    check("galla: counted 6700 vs expected 6850 = -150", abs(g.get("difference", 0) + 150.0) < 0.01, f"counted={g.get('counted')} expected={g.get('expected')} source={g.get('source')}")
    check("galla message", "150 kam" in str(g.get("message_hi")), str(g.get("message_hi")))

    print("5. morning brief + reorder (slide 6, 7:00 am)")
    b = c.get("/api/brief/today").json()
    check("brief mentions yesterday's Rs8,420", "8,420" in str(b.get("text")), str(b.get("text"))[:90])
    check("brief mentions ghee", "ghee" in str(b.get("text")).lower())
    d = post("/api/reorder/draft").json()
    ghee = [o for o in d.get("orders", []) if any("ghee" in ln.get("name", "").lower() for ln in o.get("lines", []))]
    check("reorder drafts a PO that includes ghee", bool(ghee))
    if ghee:
        sent = post(f"/api/reorder/{ghee[0]['action_id']}/send", json={}).json()
        check("PO sent to supplier over WhatsApp", bool(sent.get("message", {}).get("id")))

    print("6. WhatsApp voice order + ask the munim")
    wa = post("/api/wa/simulate-inbound", data={"type": "audio", "from_phone": "919810000004", "demo_phrase": "1"}).json()
    check("customer voice note becomes a draft order", wa.get("routed") == "wa_order" and wa.get("total"), str(wa.get("routed")))
    q = post("/api/munim/ask", json={"text": "verma ji ka kitna baaki hai"}).json()
    check("munim answers the udhaar question", "1,350" in str(q.get("answer")) or "1350" in str(q.get("answer")), str(q.get("answer"))[:80])

    print("7. providers")
    h = c.get("/api/admin/health").json()
    states = {k: v.get("state") for k, v in h.get("services", {}).items()}
    print(f"    provider states: {states}")
    if args.live:
        check("Sarvam is live (not fixture)", states.get("sarvam_stt") in ("live",) and states.get("sarvam_chat") in ("live",))

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("FAILED:", *failed, sep="\n  - ")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
