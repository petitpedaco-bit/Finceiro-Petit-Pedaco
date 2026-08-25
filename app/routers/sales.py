from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import InsufficientStockError, ProductNotFoundError
from app.schemas import CheckoutRequest, SaleResponse
from app.services.sale_service import SaleService

router = APIRouter(prefix="/sales", tags=["Vendas"])


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
