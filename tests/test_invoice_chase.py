import pytest
from pydantic import ValidationError

from noesek.tools.invoice_chase import InvoiceChaseInput as I, invoice_chase as f

INV = [dict(id="A1", customer="Acme", amount="1000.00", due="2026-09-30"),
       dict(id="A2", customer="Acme", amount="250.50", due="2026-08-20", chases_sent=2),
       dict(id="B1", customer="Beta", amount="400", due="2026-07-01"),
       dict(id="C1", customer="Cee", amount="90", due="2026-10-20"),
       dict(id="D1", customer="Dee", amount="10", due="2026-06-01", paid=True)]


def run(**kw):
    return f(I(invoices=kw.pop("invoices", INV), as_of="2026-10-03", **kw))


def test_aging_totals_and_paid_skipped():
    r = run()
    assert r["open_invoices"] == 4 and r["sent"] is False
    assert r["aging"] == {"1-30": "1000.00", "31-60": "250.50", "90+": "400.00", "current": "90.00"}
    assert r["open_total"] == "1740.50" and r["overdue_total"] == "1650.50"
    assert list(r["overdue_by_customer"]) == ["Acme", "Beta"]


def test_stage_and_order():
    r = {x["id"]: x for x in run()["invoices"]}
    assert r["A1"]["stage"] == "friendly_reminder" and r["A2"]["stage"] == "firm" and r["B1"]["stage"] == "final_notice"
    assert r["C1"]["stage"] == "none" and r["C1"]["draft"] == "" and r["C1"]["due_in_days"] == 17
    assert [x["id"] for x in run()["invoices"]][0] == "B1"


def test_friendly_reminder_and_signature():
    r = run(invoices=[dict(id="X", customer="Zed", amount="75", due="2026-10-01")], sender="Ethan")
    d = r["invoices"][0]
    assert d["stage"] == "friendly_reminder" and d["draft"].endswith("Ethan") and "USD 75.00" in d["draft"]


def test_bad_inputs():
    assert run(invoices=[dict(id="X", customer="Z", amount="5", due="soon")])["skipped_bad_dates"] == ["X"]
    assert f(I(invoices=INV, as_of="10/03/2026"))["ok"] is False
    with pytest.raises(ValidationError):
        I(invoices=[dict(id="X", customer="Z", amount="-5", due="2026-01-01")], as_of="2026-10-03")
    with pytest.raises(ValidationError):
        I(invoices=[dict(id="X", customer="Z", amount="abc", due="2026-01-01")], as_of="2026-10-03")
