"""Receipts: the public HTML page, the WhatsApp text and the Hinglish voice-receipt script.

  * `receipt_html(db, invoice)`      clean mobile page served at GET /r/{token}
  * `whatsapp_text(db, invoice)`     short text receipt with the public link
  * `voice_script(db, invoice)`      "Aapne 2 Maggi, 1 Surf Excel, 4 Colgate liya, kul Rs 249"
  * `send_receipts(db, invoice)`     queue text + voice receipt through services.whatsapp.notify

GST is worked out of the MRP (prices are MRP-inclusive). Composition-scheme stores issue a
"Bill of Supply" with no tax split, see `services/pricing.py`.
"""
from __future__ import annotations

import asyncio
import html
import logging
from typing import Optional

from sqlalchemy.orm import Session

from config import settings
from models import Invoice, InvoiceItem, Message, StoreProfile
from services import invoicing, khata, tts_cache, voice_style, whatsapp

log = logging.getLogger("awaaz.receipts")

MODE_LABELS = {"upi": "UPI (Paytm)", "cash": "Cash", "khata": "Khata (udhaar)",
               "postpaid": "Paytm Postpaid", "card": "Card"}


def fmt_money(x: float) -> str:
    """249.0 -> '249'; 249.5 -> '249.50'."""
    x = round(float(x), 2)
    return f"{int(x)}" if abs(x - round(x)) < 0.005 else f"{x:.2f}"


def receipt_url(invoice: Invoice) -> str:
    return f"{settings.public_base_url}/r/{invoice.public_token}"


def absolute_url(path: Optional[str]) -> Optional[str]:
    """Turn a relative served path (/api/voice/tts/x.mp3) into a public URL."""
    if not path:
        return None
    if path.startswith("http"):
        return path
    return f"{settings.public_base_url}{path}"


# --- quantity wording ---


def fmt_qty(qty: float, unit: str) -> str:
    """Printed quantity: '2 packet', '450 g', '1.5 kg', '300 ml'."""
    unit = (unit or "").lower()
    if unit == "kg":
        return f"{int(round(qty * 1000))} g" if qty < 1 else f"{qty:g} kg"
    if unit in ("litre", "l", "ltr"):
        return f"{int(round(qty * 1000))} ml" if qty < 1 else f"{qty:g} litre"
    return f"{qty:g} {unit}".strip()


def spoken_item(it: InvoiceItem) -> str:
    """'2 Maggi', '450 gram Cheeni', '1 kilo 500 gram Chawal'."""
    unit = (it.unit or "").lower()
    if unit == "kg":
        grams = int(round(it.qty * 1000))
        if grams < 1000:
            return f"{grams} gram {it.name}"
        kilos, rem = divmod(grams, 1000)
        return f"{kilos} kilo {it.name}" if rem == 0 else f"{kilos} kilo {rem} gram {it.name}"
    if unit in ("litre", "l", "ltr"):
        ml = int(round(it.qty * 1000))
        if ml < 1000:
            return f"{ml} ml {it.name}"
        litres, rem = divmod(ml, 1000)
        return f"{litres} litre {it.name}" if rem == 0 else f"{litres} litre {rem} ml {it.name}"
    return f"{it.qty:g} {it.name}"


def _store(db: Session) -> StoreProfile:
    return invoicing.get_store(db)


def _paid_parts(invoice: Invoice) -> list[tuple[str, float]]:
    return [(p.mode, float(p.amount)) for p in invoice.payments]


# --- voice receipt ---


def voice_script(db: Session, invoice: Invoice) -> str:
    """The spoken receipt. The variant is picked from the invoice number, so the same bill always
    gets the same words (cache friendly) while different bills sound different."""
    names = [spoken_item(it) for it in invoice.items]
    items = ", ".join(names)
    khata_text = ""
    khata_amt = sum(a for m, a in _paid_parts(invoice) if m == "khata")
    if khata_amt > 0 and invoice.customer_id:
        khata_text = (f" Isme {voice_style.rs(khata_amt)} khate mein likhe hain, "
                      f"kul baaki {voice_style.rs(khata.balance(db, invoice.customer_id))}.")
    kind = "voice_receipt" if len(names) <= 4 and len(items) <= 90 else "voice_receipt_short"
    return voice_style.line(kind, seed=invoice.number, max_chars=260, items=items, count=len(names),
                            total=invoice.total, khata=khata_text, store=_store(db).name).text


# --- WhatsApp text ---


def whatsapp_text(db: Session, invoice: Invoice) -> str:
    store = _store(db)
    title = "Bill of Supply" if invoice.doc_type == "bill_of_supply" else "Tax Invoice"
    when = invoice.created_at.strftime("%d %b %Y, %I:%M %p") if invoice.created_at else ""
    lines = [f"*{store.name}*"]
    if store.address:
        lines.append(store.address)
    lines += [f"{title}: {invoice.number}", when, ""]
    for it in invoice.items:
        lines.append(f"{fmt_qty(it.qty, it.unit)} {it.name}  =  ₹{fmt_money(it.total)}")
    lines.append("")
    lines.append(f"*Kul: ₹{fmt_money(invoice.total)}*")
    if invoice.doc_type == "tax_invoice" and (invoice.cgst_total or invoice.sgst_total):
        lines.append(f"(GST shamil: CGST ₹{fmt_money(invoice.cgst_total)} + SGST ₹{fmt_money(invoice.sgst_total)})")
    parts = _paid_parts(invoice)
    if parts:
        lines.append("Bhugtan: " + ", ".join(f"{MODE_LABELS.get(m, m)} ₹{fmt_money(a)}" for m, a in parts))
    khata_amt = sum(a for m, a in parts if m == "khata")
    if khata_amt > 0 and invoice.customer_id:
        lines.append(f"Khate mein baaki: ₹{fmt_money(khata.balance(db, invoice.customer_id))}")
    lines += ["", f"Rasid: {receipt_url(invoice)}", "", "Dhanyavaad! Phir aaiyega."]
    return "\n".join(lines)


# --- public HTML page ---

_CSS = """
:root{--ink:#0f172a;--mute:#64748b;--line:#e2e8f0;--bg:#f1f5f9;--card:#fff;--blue:#00b9f5;--navy:#002e6e;--ok:#16a34a;--warn:#d97706}
@media (prefers-color-scheme:dark){:root{--ink:#e2e8f0;--mute:#94a3b8;--line:#334155;--bg:#0b1220;--card:#111a2e;--navy:#7dd3fc}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans","Noto Sans Devanagari",sans-serif;padding:16px}
.card{max-width:440px;margin:0 auto;background:var(--card);border:1px solid var(--line);border-radius:16px;overflow:hidden}
.head{padding:20px 16px 12px;text-align:center;border-bottom:1px dashed var(--line)}
.head h1{margin:0;font-size:20px;color:var(--navy)}
.head p{margin:2px 0;color:var(--mute);font-size:13px}
.doc{display:inline-block;margin-top:8px;padding:2px 10px;border-radius:99px;background:var(--navy);color:#fff;font-size:12px;letter-spacing:.04em;text-transform:uppercase}
.meta{display:flex;justify-content:space-between;gap:8px;padding:12px 16px;font-size:13px;color:var(--mute);flex-wrap:wrap}
.meta b{color:var(--ink)}
table{width:100%;border-collapse:collapse}
th,td{padding:8px 16px;text-align:right;font-size:14px}
th:first-child,td:first-child{text-align:left}
th{color:var(--mute);font-weight:600;font-size:12px;border-bottom:1px solid var(--line);text-transform:uppercase}
td.n small{display:block;color:var(--mute);font-size:12px}
tbody tr+tr td{border-top:1px solid var(--line)}
.sum{padding:8px 16px;border-top:1px solid var(--line)}
.row{display:flex;justify-content:space-between;padding:3px 0;font-size:14px}
.row.mute{color:var(--mute);font-size:13px}
.total{display:flex;justify-content:space-between;align-items:baseline;padding:14px 16px;background:var(--bg);font-weight:700;font-size:20px}
.pay{padding:10px 16px}
.pill{display:inline-block;padding:1px 9px;border-radius:99px;font-size:12px;font-weight:600}
.paid{background:#dcfce7;color:#166534}.pending{background:#fef3c7;color:#92400e}
.note{padding:12px 16px 18px;color:var(--mute);font-size:12px;text-align:center}
"""


def _row(label: str, value: str, cls: str = "") -> str:
    return f'<div class="row {cls}"><span>{label}</span><span>{value}</span></div>'


def receipt_html(db: Session, invoice: Invoice) -> str:
    store = _store(db)
    e = html.escape
    title = "Bill of Supply" if invoice.doc_type == "bill_of_supply" else "Tax Invoice"
    when = invoice.created_at.strftime("%d %b %Y, %I:%M %p") if invoice.created_at else ""
    customer = invoice.customer.name if invoice.customer and invoice.customer_id != 1 else ""

    rows = "".join(
        f'<tr><td class="n">{e(it.name)}<small>{e(it.name_hi or "")}</small></td>'
        f'<td>{e(fmt_qty(it.qty, it.unit))}</td><td>₹{fmt_money(it.mrp)}</td>'
        f'<td>₹{fmt_money(it.total)}</td></tr>' for it in invoice.items)

    summary = []
    if invoice.doc_type == "tax_invoice":
        summary.append(_row("Taxable value", f"₹{fmt_money(invoice.taxable_total)}"))
        by_rate: dict[float, list[float]] = {}
        for it in invoice.items:
            agg = by_rate.setdefault(float(it.gst_rate or 0.0), [0.0, 0.0])
            agg[0] += it.cgst
            agg[1] += it.sgst
        for rate in sorted(by_rate):
            if rate <= 0:
                continue
            c, s = by_rate[rate]
            summary.append(_row(f"CGST @ {rate / 2:g}%", f"₹{fmt_money(c)}", "mute"))
            summary.append(_row(f"SGST @ {rate / 2:g}%", f"₹{fmt_money(s)}", "mute"))
        summary.append(_row("Total GST", f"₹{fmt_money(invoice.cgst_total + invoice.sgst_total)}"))
    else:
        summary.append(_row("Tax", "Nil (composition dealer)", "mute"))

    pay_rows = "".join(
        _row(e(MODE_LABELS.get(p.mode, p.mode)),
             f'₹{fmt_money(p.amount)} <span class="pill {"paid" if p.status == "success" else "pending"}">'
             f'{"Paid" if p.status == "success" else "Pending"}</span>') for p in invoice.payments)
    status_pill = ('<span class="pill paid">Paid</span>' if invoice.status == "paid"
                   else '<span class="pill pending">Payment pending</span>')

    if invoice.doc_type == "bill_of_supply":
        footer = ("Composition taxable person, not eligible to collect tax on supplies. "
                  "Prices are MRP.")
    else:
        footer = "Prices are MRP inclusive of GST. GST is worked out of the MRP."
    gstin = f"<p>GSTIN: {e(store.gstin)}</p>" if store.gstin else ""
    phone = f"<p>Ph: {e(store.phone)}</p>" if store.phone else ""
    cust = f"<span>Customer: <b>{e(customer)}</b></span>" if customer else ""

    return f"""<!doctype html>
<html lang="hi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{e(title)} {e(invoice.number)} | {e(store.name)}</title>
<style>{_CSS}</style></head>
<body><div class="card">
<div class="head"><h1>{e(store.name)}</h1><p>{e(store.address or "")}</p>{gstin}{phone}
<span class="doc">{e(title)}</span></div>
<div class="meta"><span>Bill no: <b>{e(invoice.number)}</b></span><span>{e(when)}</span>{cust}</div>
<table><thead><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>{rows}</tbody></table>
<div class="sum">{"".join(summary)}</div>
<div class="total"><span>Total</span><span>₹{fmt_money(invoice.total)}</span></div>
<div class="pay">{_row("Status", status_pill)}{pay_rows}</div>
<div class="note">{e(footer)}<br>Dhanyavaad! Phir aaiyega.</div>
</div></body></html>"""


def not_found_html() -> str:
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width,initial-scale=1"><title>Rasid nahi mili</title></head>'
            '<body style="font-family:sans-serif;padding:24px;text-align:center">'
            '<h2>Rasid nahi mili</h2><p>Yeh link galat ya purana hai.</p></body></html>')


# --- sending ---


async def send_receipts(db: Session, invoice: Invoice, to: Optional[str] = None,
                        voice: bool = True) -> list[Message]:
    """Queue the text receipt and the voice receipt for the invoice's customer (or `to`).
    Returns the queued messages; [] when there is nobody to send to. Never raises."""
    customer = invoice.customer
    phone = to or (customer.phone if customer else None)
    if not phone:
        return []
    out: list[Message] = []
    try:
        out.append(whatsapp.notify(db, phone, whatsapp_text(db, invoice), type="text",
                                   customer_id=invoice.customer_id))
        if voice:
            script = voice_script(db, invoice)
            lang = (customer.language if customer and customer.language else "hi-IN")
            key = tts_cache.key_of_line(script, lang, None, RECEIPT_PACE)
            cached = tts_cache.get_cached(key)
            if cached or not tts_cache.available():
                # instant: the clip exists, or there is no TTS and the audio message carries the text
                out.append(whatsapp.notify(db, phone, script, type="audio",
                                           customer_id=invoice.customer_id,
                                           media_ref=absolute_url(cached)))
            else:
                # never make the payment wait for TTS: the voice note follows when the clip is ready
                _send_voice_later(phone, script, lang, invoice.customer_id)
    except Exception:  # messaging must never break a sale
        log.exception("receipt send failed for invoice %s", invoice.number)
    return out


RECEIPT_PACE = 0.97
_pending_voice: set = set()


def _send_voice_later(phone: str, script: str, lang: str, customer_id: Optional[int]) -> None:
    async def job() -> None:
        from database import SessionLocal  # local: keeps module import light

        try:
            sp = await tts_cache.ensure(script, lang, None, RECEIPT_PACE)
            db = SessionLocal()
            try:
                whatsapp.notify(db, phone, script, type="audio", customer_id=customer_id,
                                media_ref=absolute_url(sp.url))
                db.commit()
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            log.exception("deferred voice receipt failed")

    try:
        task = asyncio.get_running_loop().create_task(job())
    except RuntimeError:
        return
    _pending_voice.add(task)
    task.add_done_callback(_pending_voice.discard)
