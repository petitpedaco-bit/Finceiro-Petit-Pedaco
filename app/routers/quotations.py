import re
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.database import get_session
from app.models import Product, QuotationWorkbook
from app.services.google_sheet_service import download_google_sheet
from app.services.workbook_service import QuotationBook, WorkbookCalculator, read_workbook, workbook_quotations
from app.services.quotation_service import QuotationRow, read_quotations
from app.services.quotation_catalog import search_catalog
from app.schemas import ProductResponse

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
        data = await download_google_sheet(payload.url)
        return await run_in_threadpool(read_quotations, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, 'O Google não respondeu à exportação. Tente novamente em instantes.') from exc


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


class SaveWorkbook(BaseModel):
    id: uuid.UUID | None = None
    version: int = Field(default=0, ge=0)
    title: str = Field(min_length=1, max_length=160)
    source_url: str | None = Field(default=None, max_length=500)
    book: QuotationBook
    bindings: dict[str, str] = Field(default_factory=dict, max_length=250)
    sync_sheets: list[str] = Field(default_factory=list, max_length=250)
    update_sale_prices: bool = False


@router.get('/products')
async def quotation_products(search: str = Query(default='', max_length=160),
                             session: AsyncSession = Depends(get_session)) -> list[dict]:
    documents = (await session.scalars(select(QuotationWorkbook)
        .order_by(QuotationWorkbook.updated_at.desc(), QuotationWorkbook.id.desc()))).all()
    rows = await run_in_threadpool(search_catalog, [
        {'id': document.id, 'title': document.title, 'data': document.data,
         'bindings': document.bindings} for document in documents], search)
    if not rows:
        return []
    products = (await session.scalars(select(Product).where(
        Product.sku.in_([row['sku'] for row in rows])))).all()
    by_sku = {product.sku: ProductResponse.model_validate(product).model_dump(mode='json')
              for product in products}
    return [{**row, 'product': by_sku.get(row['sku'])} for row in rows]


@router.post('/workbook/calculate')
async def calculate_workbook(book: QuotationBook) -> dict:
    warnings = await run_in_threadpool(WorkbookCalculator(book).calculate)
    preview = await run_in_threadpool(workbook_quotations, book)
    return {'book': book.model_dump(mode='json'), 'rows': preview['rows'],
        'warnings': warnings + preview['warnings']}


@router.post('/workbook/google')
async def google_workbook(payload: GoogleQuotation) -> dict:
    try:
        content = await download_google_sheet(payload.url)
        return {'book': await run_in_threadpool(read_workbook, content)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, 'Falha temporária ao baixar a planilha do Google. Tente novamente.') from exc


@router.post('/workbook/excel')
async def excel_workbook(file: UploadFile) -> dict:
    try:
        return {'book': await run_in_threadpool(read_workbook, await file.read(20 * 1024 * 1024 + 1))}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/documents')
async def list_workbooks(session: AsyncSession = Depends(get_session)) -> list[dict]:
    result = await session.execute(select(QuotationWorkbook.id, QuotationWorkbook.title,
        QuotationWorkbook.version, QuotationWorkbook.updated_at).order_by(QuotationWorkbook.updated_at.desc()))
    return [dict(row._mapping) for row in result]


@router.get('/documents/{document_id}')
async def get_workbook(document_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    document = await session.get(QuotationWorkbook, document_id)
    if document is None:
        raise HTTPException(404, 'Cotação não encontrada')
    return {'id': document.id, 'title': document.title, 'version': document.version,
        'source_url': document.source_url, 'book': document.data, 'bindings': document.bindings}


@router.post('/documents/save')
async def save_workbook(payload: SaveWorkbook, session: AsyncSession = Depends(get_session)) -> dict:
    warnings = await run_in_threadpool(WorkbookCalculator(payload.book).calculate)
    preview = await run_in_threadpool(workbook_quotations, payload.book)
    valid_rows = {row['sheet']: row for row in preview['rows']}
    selected = set(payload.sync_sheets)
    if selected - set(valid_rows):
        raise HTTPException(422, 'Há fichas selecionadas com cálculo incompleto. Salve sem sincronizar e revise os avisos.')
    if set(payload.bindings) - {sheet.name for sheet in payload.book.sheets}:
        raise HTTPException(422, 'Vínculo aponta para uma aba inexistente')
    if any(not sku.strip() or len(sku) > 64 for sku in payload.bindings.values()):
        raise HTTPException(422, 'SKU deve ter entre 1 e 64 caracteres')
    sync_rows = [QuotationRow.model_validate({**valid_rows[name], 'sku': payload.bindings.get(name, valid_rows[name]['sku'])}) for name in sorted(selected)]
    if len({row.sku for row in sync_rows}) != len(sync_rows):
        raise HTTPException(422, 'Há SKUs repetidos nas fichas selecionadas')
    created = updated = 0
    async with session.begin():
        from sqlalchemy import text
        await session.execute(text('SELECT pg_advisory_xact_lock(734901)'))
        document = None
        if payload.id:
            document = await session.scalar(select(QuotationWorkbook).where(QuotationWorkbook.id == payload.id).with_for_update())
            if document is None:
                raise HTTPException(404, 'Cotação não encontrada')
            if document.version != payload.version:
                raise HTTPException(409, 'Esta cotação mudou em outra sessão. Reabra antes de salvar.')
            document.version += 1
        else:
            document = QuotationWorkbook(version=1)
            session.add(document)
        document.title = payload.title
        document.source_url = payload.source_url
        document.data = payload.book.model_dump(mode='json')
        document.bindings = {**payload.bindings, **{row.sheet: row.sku for row in sync_rows}}
        for row in sorted(sync_rows, key=lambda row: row.sku):
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
        await session.flush()
        output = {'id': str(document.id), 'version': document.version, 'book': document.data,
            'bindings': document.bindings, 'rows': preview['rows'], 'warnings': warnings + preview['warnings'],
            'created': created, 'updated': updated}
    return output
