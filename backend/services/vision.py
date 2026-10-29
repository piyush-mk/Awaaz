"""Image understanding: photo in, structured JSON out.

`extract_json_from_image(image_bytes, mime, task)` runs the chain
Sarvam gemma4 -> xAI grok-4.3 -> deterministic fixture and returns a `Result`
whose `data` is already normalised to the task's shape:

  shelf          [{name, quantity}]
  purchase_bill  {supplier, bill_no, date, lines:[{name, qty, unit, rate, mrp, batch,
                  expiry, scheme_text, free_qty}]}
  parchi         [{name, qty, unit}]
  khata_page     [{customer, amount, date, note}]
  cash           {denominations:{2000,500,200,100,50,20,10,coins}, total, confidence}
                 (coins is the rupee VALUE of loose coins, notes are counts)
"""
from __future__ import annotations

import json
import re
from typing import Any

from config import settings
from services import fixtures, sarvam, xai
from services.types import ProviderError, Result, Timer

Task = str
TASKS = ("shelf", "purchase_bill", "parchi", "khata_page", "cash")
NOTE_DENOMS = (2000, 500, 200, 100, 50, 20, 10)

_BASE = ("You are reading a photo for an Indian kirana (grocery) shop. "
         "Never invent items that are not visible. Use null for unreadable fields. ")

PROMPTS: dict[str, str] = {
    "shelf": _BASE + "Identify every product visible on the shelf and count the visible units of each "
             "(count facings and stacked units; do not count the same item twice). "
             "Use brand names when visible. Return a JSON array of {name, quantity}.",
    "purchase_bill": _BASE + "This is a distributor purchase invoice. Extract the supplier name, bill "
                     "number, date (YYYY-MM-DD) and every line: name, qty, unit, rate (per unit cost), "
                     "mrp, batch, expiry (YYYY-MM-DD; convert MM/YY to the last day of that month), "
                     "scheme_text (e.g. 'Buy 10 Get 1 Free' or '10+1', empty if none) and free_qty "
                     "(free units actually listed as delivered on the bill, 0 if none). Copy numbers "
                     "exactly as printed; rate is the per-unit price the shop pays, not the line total.",
    "parchi": _BASE + "This is a handwritten shopping list (parchi), often in Hindi. Transliterate each "
              "item to common Hinglish (e.g. cheeni, doodh, dal, maggi) and return a JSON array of "
              "{name, qty, unit}. qty is a number (use 1 when none is written); unit is one of "
              "kg, g, litre, ml, packet, dozen, or empty if unclear. One entry per line of the list.",
    "khata_page": _BASE + "This is a page of a handwritten credit ledger (khata). Return a JSON array "
                  "of {customer, amount, date, note} where amount is the outstanding rupees.",
    "cash": _BASE + "This is a photo of cash spread on a counter. Count the notes of each denomination "
            "separately (2000, 500, 200, 100, 50, 20, 10) and give the total rupee value of loose coins "
            "under 'coins'. Fill the table row by row. Include an overall 'confidence' between 0 and 1 "
            "and a 'denomination_confidence' object with a 0-1 confidence for each denomination key "
            "(lower it for stacked or overlapping notes and for look-alike 10/20/50 notes).",
}

_STR = {"type": ["string", "null"]}
SCHEMAS: dict[str, dict] = {
    "shelf": {"type": "array", "items": {"type": "object", "required": ["name", "quantity"],
              "properties": {"name": {"type": "string"}, "quantity": {"type": "number"}}}},
    "purchase_bill": {"type": "object", "properties": {
        "supplier": _STR, "bill_no": _STR, "date": _STR,
        "lines": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "qty": {"type": "number"}, "unit": _STR,
            "rate": {"type": "number"}, "mrp": {"type": ["number", "null"]}, "batch": _STR,
            "expiry": _STR, "scheme_text": _STR, "free_qty": {"type": ["number", "null"]}}}}}},
    "parchi": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "qty": {"type": "number"}, "unit": _STR}}},
    "khata_page": {"type": "array", "items": {"type": "object", "properties": {
        "customer": {"type": "string"}, "amount": {"type": "number"}, "date": _STR, "note": _STR}}},
    "cash": {"type": "object", "properties": {
        "denominations": {"type": "object", "properties": {
            **{str(d): {"type": "integer"} for d in NOTE_DENOMS}, "coins": {"type": "number"}}},
        "confidence": {"type": "number"},
        "denomination_confidence": {"type": "object", "additionalProperties": {"type": "number"}}}},
}


def parse_json_loose(text: str) -> Any:
    """Extract the first JSON value from model output (fences and chatter tolerated)."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = t.find(open_c), t.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(t[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ProviderError("vision output is not valid JSON", "vision")


def cash_total(denominations: dict[str, Any]) -> float:
    """Rupee value of a denominations table (notes are counts, `coins` is a value)."""
    total = 0.0
    for d in NOTE_DENOMS:
        total += d * float(denominations.get(str(d), 0) or 0)
    return total + float(denominations.get("coins", 0) or 0)


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def normalize_result(task: str, data: Any) -> Any:
    """Coerce model output into the task's documented shape (raises ProviderError if hopeless)."""
    if task in ("shelf", "parchi", "khata_page"):
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        if not isinstance(data, list):
            raise ProviderError(f"{task}: expected a list", "vision")
        rows = []
        for r in data:
            if not isinstance(r, dict):
                continue
            if task == "shelf":
                name = str(r.get("name") or "").strip()
                if name:
                    rows.append({"name": name, "quantity": max(1, int(_num(r.get("quantity"), 1)))})
            elif task == "parchi":
                name = str(r.get("name") or "").strip()
                if name:
                    rows.append({"name": name, "qty": _num(r.get("qty"), 1) or 1.0,
                                 "unit": r.get("unit") or ""})
            else:
                name = str(r.get("customer") or "").strip()
                if name:
                    rows.append({"customer": name, "amount": _num(r.get("amount")),
                                 "date": r.get("date") or None, "note": r.get("note") or ""})
        return rows
    if task == "purchase_bill":
        if isinstance(data, list):
            data = {"lines": data}
        if not isinstance(data, dict):
            raise ProviderError("purchase_bill: expected an object", "vision")
        lines = []
        for r in data.get("lines") or []:
            if isinstance(r, dict) and str(r.get("name") or "").strip():
                lines.append({
                    "name": str(r["name"]).strip(), "qty": _num(r.get("qty")), "unit": r.get("unit") or "",
                    "rate": _num(r.get("rate")), "mrp": (None if r.get("mrp") is None else _num(r.get("mrp"))),
                    "batch": r.get("batch") or "", "expiry": r.get("expiry") or None,
                    "scheme_text": r.get("scheme_text") or "", "free_qty": _num(r.get("free_qty")),
                })
        return {"supplier": data.get("supplier"), "bill_no": data.get("bill_no"),
                "date": data.get("date"), "lines": lines}
    if task == "cash":
        if not isinstance(data, dict):
            raise ProviderError("cash: expected an object", "vision")
        raw = data.get("denominations") if isinstance(data.get("denominations"), dict) else data
        denoms = {str(d): int(_num(raw.get(str(d)) if str(d) in raw else raw.get(d), 0)) for d in NOTE_DENOMS}
        denoms["coins"] = _num(raw.get("coins"), 0)
        per_denom = data.get("denomination_confidence")
        per_denom = ({k: min(1.0, max(0.0, _num(per_denom.get(k), 0.5)))
                      for k in (*(str(d) for d in NOTE_DENOMS), "coins") if k in per_denom}
                     if isinstance(per_denom, dict) else {})
        return {"denominations": denoms, "total": cash_total(denoms),
                "confidence": min(1.0, max(0.0, _num(data.get("confidence"), 0.5))),
                "denomination_confidence": per_denom}
    raise ValueError(f"unknown vision task: {task}")


async def extract_json_from_image(image_bytes: bytes, mime: str, task: Task) -> Result[Any]:
    """Photo -> normalised JSON for `task`. Chain: sarvam -> xai -> fixture."""
    if task not in TASKS:
        raise ValueError(f"unknown vision task: {task}")
    prompt, schema = PROMPTS[task], SCHEMAS[task]
    errors: list[str] = []
    if not settings.fixtures_only:
        for name, available, call in (("sarvam", settings.has_sarvam, sarvam.vision),
                                      ("xai", settings.has_xai, xai.vision)):
            if not available:
                continue
            try:
                with Timer() as t:
                    raw = await call(image_bytes, mime, prompt, schema)
                    data = normalize_result(task, parse_json_loose(raw.data))
                return Result(data, name, t.ms)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001 - try the next provider
                errors.append(f"{name}: {str(exc)[:150]}")
    if not settings.fixtures_allowed:
        raise ProviderError("; ".join(errors) or "no vision provider configured", "vision")
    return Result(normalize_result(task, fixtures.vision_fixture(task)), "fixture", 0,
                  {"errors": errors} if errors else {})
