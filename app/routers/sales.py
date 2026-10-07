from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import InsufficientStockError, ProductNotFoundError
from app.models import Sale
from app.schemas import CheckoutRequest, SaleResponse, SaleSummary
from app.services.sale_service import SaleService

router = APIRouter(prefix="/sales", tags=["Vendas"])


@router.get("", response_model=list[SaleSummary])
async def list_sales(session: AsyncSession = Depends(get_session)) -> list[SaleSummary]:
    result = await session.execute(select(Sale).order_by(Sale.created_at.desc()))
    return [SaleSummary.model_validate(sale) for sale in result.scalars()]


@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_sale(sale_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> None:
    try:
        await SaleService(session).cancel(sale_id)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/checkout", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def checkout(payload: CheckoutRequest, session: AsyncSession = Depends(get_session)) -> SaleResponse:
    try:
        sale = await SaleService(session).checkout(payload)
        return SaleResponse.model_validate(sale)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InsufficientStockError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
import uuid

