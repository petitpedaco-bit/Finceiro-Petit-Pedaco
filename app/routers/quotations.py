import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.database import get_session
from app.models import Product
from app.services.quotation_service import QuotationRow, read_quotations

router = APIRouter(prefix='/quotations', tags=['Cotações'])


class GoogleQuotation(BaseModel):
    url: str = Field(max_length=500)


class ApplyQuotation(BaseModel):
    rows: list[QuotationRow] = Field(min_length=1, max_length=500)
    update_sale_prices: bool = False


@router.post('/preview/google')
async def google_preview(payload: GoogleQuotation) -> dict:
    match = re.fullmatch(r'https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)/.*', payload.url)
    if not match:
        raise HTTPException(422, 'Informe um link de planilha Google Sheets')
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Endpoint fixo impede requisições a endereços fornecidos pelo usuário.
            async with client.stream('GET', f'https://docs.google.com/spreadsheets/d/{match[1]}/export?format=xlsx') as response:
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 20 * 1024 * 1024:
                        raise ValueError('Arquivo excede 20 MB')
        return await run_in_threadpool(read_quotations, bytes(data))
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(422, 'Não foi possível ler a exportação pública. Use o upload Excel ou verifique as permissões.') from exc


@router.post('/preview/excel')
async def excel_preview(file: UploadFile) -> dict:
    data = await file.read(20 * 1024 * 1024 + 1)
    try:
        return await run_in_threadpool(read_quotations, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('/apply')
async def apply_quotations(payload: ApplyQuotation, session: AsyncSession = Depends(get_session)) -> dict:
    if len({row.sku for row in payload.rows}) != len(payload.rows):
        raise HTTPException(422, 'Há SKUs repetidos na seleção')
    created = updated = 0
    async with session.begin():
        # Serializa importações para evitar duas criações simultâneas do mesmo SKU.
        from sqlalchemy import text
        await session.execute(text('SELECT pg_advisory_xact_lock(734901)'))
        for row in sorted(payload.rows, key=lambda row: row.sku):
            product = await session.scalar(select(Product).where(Product.sku == row.sku).with_for_update())
            if product is None:
                product = Product(name=row.name, sku=row.sku, current_stock=0, sale_price=row.sale_price)
                session.add(product)
                created += 1
            else:
                updated += 1
                if payload.update_sale_prices:
                    product.sale_price = row.sale_price
            product.cost_price = row.cost_price
            product.additional_cost = row.additional_cost
            product.target_margin_percentage = row.target_margin_percentage
    return {'created': created, 'updated': updated}
