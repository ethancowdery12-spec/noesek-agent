"""date_math: exact calendar arithmetic, no in-head guessing (item 87, batch 4).

LLMs are famously sloppy at date math ("what day is 45 days from March 18?").
This tool computes it deterministically with python-dateutil (BSD; pinned,
already transitive via croniter - now used directly). Dates only, no timezones:
'all day' calendar questions are the common case in chat.
"""
from __future__ import annotations

import re
from datetime import date

from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, Field

_UNITS = {"day": "days", "days": "days", "week": "weeks", "weeks": "weeks",
          "month": "months", "months": "months", "year": "years", "years": "years"}


class DateMathInput(BaseModel):
    op: str = Field(description="add | between | weekday")
    date: str = Field(default="today",
                      description="Base date as YYYY-MM-DD, or 'today' (default)")
    amount: int = Field(default=0, description="For add: how many units to move (negative = back)")
    unit: str = Field(default="days", description="For add: days | weeks | months | years")
    other_date: str = Field(default="", description="For between: the second date (YYYY-MM-DD or 'today')")


def _parse(raw: str) -> date:
    raw = raw.strip().lower()
    if raw in ("", "today"):
        return date.today()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError(f"date must be YYYY-MM-DD or 'today', got {raw!r}")
    return date.fromisoformat(raw)


def _fmt(d: date) -> str:
    return f"{d.strftime('%A')}, {d.isoformat()}"


def date_math(inp: DateMathInput) -> dict:
    op = inp.op.strip().lower()
    if op == "add":
        unit = _UNITS.get(inp.unit.strip().lower())
        if not unit:
            return {"error": f"unit must be days/weeks/months/years, got {inp.unit!r}"}
        base = _parse(inp.date)
        result = base + relativedelta(**{unit: inp.amount})
        return {"op": "add", "base": _fmt(base), "amount": inp.amount, "unit": unit,
                "result": _fmt(result), "result_iso": result.isoformat()}
    if op == "between":
        a, b = _parse(inp.date), _parse(inp.other_date or "today")
        days = (b - a).days
        rd = relativedelta(b, a)
        return {"op": "between", "from": _fmt(a), "to": _fmt(b), "days": days,
                "weeks": round(days / 7, 1),
                "calendar": f"{rd.years}y {rd.months}m {rd.days}d"}
    if op == "weekday":
        d = _parse(inp.date)
        return {"op": "weekday", "date": d.isoformat(), "weekday": d.strftime("%A"),
                "week": d.isocalendar().week}
    return {"error": f"unknown op {inp.op!r}", "ops": ["add", "between", "weekday"]}
