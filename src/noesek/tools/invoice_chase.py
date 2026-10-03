"""Own-code receivables aging and chase-draft planner for small businesses.

Idea from the small-business / finance plugin skills in
anthropics/knowledge-work-plugins (Apache-2.0: reconciliation, close
management); fresh implementation, no text copied. Takes the invoices you list,
buckets them by days past due, picks a chase stage for each and writes plain
draft wording. It never sends anything, never contacts a customer and never
touches an accounting system. Amounts are what you supplied.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field, field_validator


class Invoice(BaseModel):
    id: str = Field(min_length=1, max_length=60)
    customer: str = Field(min_length=1, max_length=120)
    amount: str = Field(description="decimal amount, e.g. 1250.00")
    due: str = Field(description="due date YYYY-MM-DD")
    paid: bool = False
    chases_sent: int = Field(default=0, ge=0, le=20, description="reminders already sent for this invoice")

    @field_validator("amount")
    @classmethod
    def _amt(cls, v):
        try:
            d = Decimal(v)
        except InvalidOperation as e:
            raise ValueError("amount must be a decimal number") from e
        if d <= 0 or d > Decimal("100000000"):
            raise ValueError("amount out of range")
        return v


class InvoiceChaseInput(BaseModel):
    invoices: list[Invoice] = Field(min_length=1, max_length=500)
    as_of: str = Field(description="today's date YYYY-MM-DD")
    sender: str = Field(default="", max_length=80, description="name to sign drafts with")
    currency: str = Field(default="USD", max_length=3)


BUCKETS = [("current", None, 0), ("1-30", 1, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, None)]


def _bucket(days):
    for name, lo, hi in BUCKETS:
        if (lo is None or days >= lo) and (hi is None or days <= hi):
            return name
    return "90+"


def _stage(days, sent):
    if days <= 0:
        return "none"
    if days <= 7 and sent == 0:
        return "friendly_reminder"
    if days <= 30:
        return "reminder" if sent < 2 else "firm"
    if days <= 60:
        return "firm"
    return "final_notice"


def _draft(stage, inv, days, cur, sender):
    amt = f"{cur} {Decimal(inv.amount):,.2f}"
    sign = f"\n\n{sender}" if sender else ""
    body = {
        "friendly_reminder": f"Hi {inv.customer}, a quick reminder that invoice {inv.id} for {amt} was due on {inv.due}. If it is already on its way, thank you. If anything is blocking payment, tell me and I will sort it out.",
        "reminder": f"Hi {inv.customer}, invoice {inv.id} for {amt} was due on {inv.due} and is now {days} days past due. Could you confirm when payment will go out?",
        "firm": f"Hi {inv.customer}, invoice {inv.id} for {amt} is {days} days past due (due {inv.due}). Please pay it this week or tell me the date you will, so we can keep your account in good standing.",
        "final_notice": f"Hi {inv.customer}, invoice {inv.id} for {amt} is {days} days past due (due {inv.due}). This is a final notice before we review next steps on the account. Please reply with payment details or a payment date.",
    }[stage]
    return body + sign


def invoice_chase(inp: InvoiceChaseInput) -> dict:
    try:
        today = date.fromisoformat(inp.as_of)
    except ValueError:
        return {"ok": False, "error": "as_of must be YYYY-MM-DD", "sent": False}
    rows, bad = [], []
    for i in inp.invoices:
        try:
            due = date.fromisoformat(i.due)
        except ValueError:
            bad.append(i.id)
            continue
        if i.paid:
            continue
        days = (today - due).days
        st = _stage(days, i.chases_sent)
        rows.append({"id": i.id, "customer": i.customer, "amount": f"{Decimal(i.amount):.2f}", "days_past_due": max(days, 0),
                     "due_in_days": max(-days, 0), "bucket": _bucket(days), "stage": st,
                     "draft": _draft(st, i, days, inp.currency, inp.sender) if st != "none" else ""})
    totals = {}
    for r in rows:
        totals[r["bucket"]] = totals.get(r["bucket"], Decimal(0)) + Decimal(r["amount"])
    by_cust = {}
    for r in rows:
        if r["days_past_due"] > 0:
            by_cust[r["customer"]] = by_cust.get(r["customer"], Decimal(0)) + Decimal(r["amount"])
    rows.sort(key=lambda r: (-r["days_past_due"], -Decimal(r["amount"])))
    return {"ok": True, "as_of": inp.as_of, "open_invoices": len(rows),
            "open_total": f"{sum((Decimal(r['amount']) for r in rows), Decimal(0)):.2f}",
            "overdue_total": f"{sum(by_cust.values(), Decimal(0)):.2f}",
            "aging": {k: f"{v:.2f}" for k, v in sorted(totals.items())},
            "overdue_by_customer": {k: f"{v:.2f}" for k, v in sorted(by_cust.items(), key=lambda kv: -kv[1])},
            "invoices": rows, "skipped_bad_dates": bad, "sent": False,
            "caveat": "Drafts only. Nothing was sent or posted. Check each invoice against your books and the customer's payment terms before sending."}
