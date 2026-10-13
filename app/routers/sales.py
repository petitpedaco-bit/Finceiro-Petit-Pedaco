import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import InsufficientStockError, ProductNotFoundError
from app.models import Product, Sale, SaleItem
from app.schemas import CheckoutRequest, SaleResponse, SaleSummary
from app.services.sale_service import SaleService

router = APIRouter(prefix="/sales", tags=["Vendas"])


@router.get('/history')
async def sales_history(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                        state: str = Query('ALL', pattern='^(ALL|ACTIVE|CANCELLED)$'),
                        session: AsyncSession = Depends(get_session)) -> dict:
    conditions = []
    if state != 'ALL':
        conditions.append(Sale.is_cancelled.is_(state == 'CANCELLED'))
    total = await session.scalar(select(func.count()).select_from(Sale).where(*conditions))
    sales = list((await session.scalars(select(Sale).where(*conditions).order_by(
        Sale.created_at.desc(), Sale.id.desc()).offset(offset).limit(limit))).all())
    details = {sale.id: [] for sale in sales}
    if sales:
        rows = (await session.execute(select(SaleItem.sale_id, SaleItem.quantity, Product.name, Product.sku).outerjoin(
            Product, Product.id == SaleItem.product_id).where(SaleItem.sale_id.in_(details)).order_by(
            SaleItem.sale_id, Product.name, SaleItem.id))).all()
        for row in rows:
            details[row.sale_id].append(dict(quantity=row.quantity, name=row.name or 'Produto removido', sku=row.sku or ''))
    return dict(total=total, items=[dict(**SaleSummary.model_validate(sale).model_dump(mode='json'),
        products=details[sale.id], cancelled_at=sale.cancelled_at.isoformat() if sale.cancelled_at else None) for sale in sales])


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

