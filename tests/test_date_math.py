"""date_math tool (batch 4, item 87)."""
from datetime import date

import pytest

from noesek.tools.date_math import DateMathInput, date_math


def test_add_days_and_weeks():
    out = date_math(DateMathInput(op="add", date="2026-03-18", amount=45, unit="days"))
    assert out["result_iso"] == "2026-05-02" and "Saturday" in out["result"]
    out = date_math(DateMathInput(op="add", date="2026-09-24", amount=-2, unit="weeks"))
    assert out["result_iso"] == "2026-09-10"


def test_add_months_clamps_month_end():
    # Jan 31 + 1 month must clamp to Feb 28/29, never crash or roll into March
    out = date_math(DateMathInput(op="add", date="2026-01-31", amount=1, unit="months"))
    assert out["result_iso"] == "2026-02-28"


def test_between():
    out = date_math(DateMathInput(op="between", date="2026-01-01", other_date="2026-09-24"))
    assert out["days"] == 266 and out["weeks"] == 38.0
    assert out["calendar"] == "0y 8m 23d"


def test_weekday():
    out = date_math(DateMathInput(op="weekday", date="2026-09-24"))
    assert out["weekday"] == "Thursday" and out["week"] == 39


def test_today_default_and_bad_input():
    out = date_math(DateMathInput(op="weekday"))
    assert out["date"] == date.today().isoformat()
    with pytest.raises(ValueError):
        date_math(DateMathInput(op="add", date="next friday", amount=1))
    assert "error" in date_math(DateMathInput(op="bogus"))
