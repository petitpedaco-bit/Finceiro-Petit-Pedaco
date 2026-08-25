from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import ABCCurveResponse, CashFlowResponse, DREResponse
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Relatórios e BI"])


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
