from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import ABCCurveResponse, CashFlowResponse, DREResponse
from app.services.report_service import ReportService
from sqlalchemy import func, select
from app.models import CashFlowTransaction, CashFlowType
from app.services.report_service import period_bounds

router = APIRouter(prefix="/reports", tags=["Relatórios e BI"])


@router.get('/expense-breakdown')
async def expense_breakdown(start_date:date=Query(...),end_date:date=Query(...),session:AsyncSession=Depends(get_session)) -> dict:
    validate_period(start_date,end_date)
    start,end=period_bounds(start_date,end_date)
    rows=await session.execute(select(CashFlowTransaction.expense_nature,CashFlowTransaction.expense_behavior,
        func.sum(CashFlowTransaction.amount).label('amount'),func.count().label('count')).where(
        CashFlowTransaction.transaction_type==CashFlowType.EXPENSE,
        CashFlowTransaction.occurred_at>=start,CashFlowTransaction.occurred_at<end
    ).group_by(CashFlowTransaction.expense_nature,CashFlowTransaction.expense_behavior))
    return {'groups':[dict(row._mapping) for row in rows],
        'notice':'Classificação gerencial dos pagamentos. Não é CMV e não muda o cálculo da DRE nem faz rateio automático.'}


def validate_period(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date não pode ser anterior a start_date")


@router.get("/dre", response_model=DREResponse)
async def dre(
    start_date: date = Query(...), end_date: date = Query(...), session: AsyncSession = Depends(get_session)
) -> DREResponse:
    validate_period(start_date, end_date)
    return await ReportService(session).get_dre(start_date, end_date)


@router.get("/abc-curve", response_model=ABCCurveResponse)
async def abc_curve(
    start_date: date = Query(...), end_date: date = Query(...), session: AsyncSession = Depends(get_session)
) -> ABCCurveResponse:
    validate_period(start_date, end_date)
    return await ReportService(session).get_abc_curve(start_date, end_date)


@router.get("/cash-flow", response_model=CashFlowResponse)
async def cash_flow(
    start_date: date = Query(...), end_date: date = Query(...), session: AsyncSession = Depends(get_session)
) -> CashFlowResponse:
    validate_period(start_date, end_date)
    return await ReportService(session).get_cash_flow(start_date, end_date)
