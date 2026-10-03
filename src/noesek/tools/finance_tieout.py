"""Original Decimal capital-account tie-out from NAV audit workflow.
No paid data, finance connections, statement edits, advice or money moves.
"""
from decimal import Decimal
from pydantic import BaseModel,Field,field_validator

class FinanceTieoutInput(BaseModel):
    beginning:Decimal
    contributions:Decimal
    distributions:Decimal
    realized_pnl:Decimal
    unrealized_pnl:Decimal
    management_fee:Decimal
    fund_expenses:Decimal
    ownership_fraction:Decimal
    carried_interest:Decimal
    reported_ending:Decimal
    source_refs:list[str]=Field(min_length=1,max_length=20)
    @field_validator('beginning','contributions','distributions','realized_pnl','unrealized_pnl','management_fee','fund_expenses','ownership_fraction','carried_interest','reported_ending')
    @classmethod
    def finite_bounded(cls,value):
        if not value.is_finite() or abs(value)>Decimal('1e15'):raise ValueError('finite bounded Decimal required')
        return value
    @field_validator('source_refs')
    @classmethod
    def refs(cls,value):
        if any(not x.strip() or len(x)>500 for x in value):raise ValueError('exact nonblank source refs required')
        return value

def finance_tieout(inp):
    if not 0<=inp.ownership_fraction<=1:return {'ok':False,'error':'ownership fraction must be between 0 and 1'}
    if any(v<0 for v in [inp.contributions,inp.distributions,inp.management_fee,inp.fund_expenses,inp.carried_interest]):
        return {'ok':False,'error':'cash flows/fees must be nonnegative; use P&L sign for losses'}
    net=inp.realized_pnl+inp.unrealized_pnl-inp.management_fee-inp.fund_expenses
    allocated=inp.ownership_fraction*net
    computed=inp.beginning+inp.contributions-inp.distributions+allocated-inp.carried_interest
    difference=inp.reported_ending-computed
    return {'ok':True,'state':'pass' if abs(difference)<=Decimal('.01') else 'fail',
        'net_fund_pnl':str(net),'allocated_pnl':str(allocated),'computed_ending':str(computed),
        'reported_ending':str(inp.reported_ending),'difference':str(difference),'tolerance':'0.01',
        'source_refs':inp.source_refs,'source_trust':'caller_supplied_unverified',
        'statement_changed':False,'money_moved':False,
        'caveat':'Arithmetic tie-out of supplied figures, not verification of the NAV pack, ownership basis, accounting policy or investment result. Review source lines and obtain qualified review before distribution.'}
