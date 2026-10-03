import pytest
from noesek.tools.finance_tieout import FinanceTieoutInput,finance_tieout

def base(**kw):
    args=dict(beginning='100',contributions='10',distributions='5',realized_pnl='10',unrealized_pnl='2',management_fee='1',fund_expenses='1',ownership_fraction='.5',carried_interest='1',reported_ending='109',source_refs=['nav:Q1'])
    return FinanceTieoutInput(**(args|kw))
def test_decimal_recompute_and_mismatch():
    out=finance_tieout(base());assert out['state']=='pass' and out['computed_ending']=='109.0'
    out=finance_tieout(base(reported_ending='109.02'));assert out['state']=='fail' and not out['money_moved']
def test_unknown_missing_not_zero():
    with pytest.raises(ValueError):FinanceTieoutInput(beginning='100')
    with pytest.raises(ValueError):base(realized_pnl='NaN')
    assert not finance_tieout(base(ownership_fraction='2'))['ok']
    assert not finance_tieout(base(management_fee='-1'))['ok']
