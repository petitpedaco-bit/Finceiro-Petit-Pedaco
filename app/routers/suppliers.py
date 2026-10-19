import hashlib
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, text, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.models import Supplier, SupplierProduct, PurchaseReceipt, CashFlowTransaction, CashFlowType, PaymentMethod
from app.services.receipt_service import normalize, parse_receipt

router = APIRouter(prefix='/suppliers', tags=['Fornecedores e cupons'])


class ReceiptText(BaseModel):
    text: str = Field(min_length=1, max_length=60000)


class PurchaseItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=160)
    unit: str = Field(default='UN', min_length=1, max_length=16)
    quantity: Decimal = Field(gt=0, le=1000000, max_digits=14, decimal_places=4)
    total: Decimal = Field(gt=0, le=99999999, max_digits=14, decimal_places=2)


class ReceiptInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    supplier_name: str = Field(min_length=1, max_length=160)
    cnpj: str = Field(default='', pattern=r'^(\d{14})?$')
    supplier_id: uuid.UUID | None = None
    fiscal_key: str = Field(default='', pattern=r'^(\d{44})?$')
    number: str = Field(min_length=1, max_length=80)
    date: date
    amount: Decimal = Field(gt=0, le=99999999, max_digits=14, decimal_places=2)
    items: list[PurchaseItem] = Field(min_length=1, max_length=200)
    create_expense: bool = False
    cash_transaction_id: uuid.UUID | None = None
    payment_method: PaymentMethod = PaymentMethod.PIX
    reviewed: bool = False


@router.post('/receipts/preview')
async def preview_receipt(payload: ReceiptText):
    return parse_receipt(payload.text)


@router.get('')
async def list_suppliers(session: AsyncSession = Depends(get_session)):
    return [dict(id=str(row.id), name=row.name, cnpj=row.cnpj or '') for row in
        (await session.scalars(select(Supplier).order_by(Supplier.name).limit(1000))).all()]


@router.get('/{supplier_id}/products')
async def supplier_products(supplier_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return [dict(id=str(row.id), name=row.name, unit=row.unit, unit_price=str(row.unit_price), price_date=row.price_date.isoformat())
        for row in (await session.scalars(select(SupplierProduct).where(SupplierProduct.supplier_id == supplier_id)
            .order_by(SupplierProduct.name).limit(1000))).all()]


@router.get('/receipts/history')
async def receipt_history(offset: int = Query(0, ge=0), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(PurchaseReceipt, Supplier.name).join(Supplier)
        .order_by(PurchaseReceipt.occurred_at.desc(), PurchaseReceipt.created_at.desc()).offset(offset).limit(20))).all()
    return dict(total=await session.scalar(select(func.count()).select_from(PurchaseReceipt)), items=[
        dict(id=str(row.id), supplier=name, number=row.number, date=row.occurred_at.date().isoformat(), amount=str(row.amount),
            items=row.items, cash_transaction_id=str(row.cash_transaction_id) if row.cash_transaction_id else None)
        for row, name in rows])


@router.get('/receipts/candidates')
async def receipt_expenses(purchase_date: date, amount: Decimal = Query(gt=0), session: AsyncSession = Depends(get_session)):
    when = datetime.combine(purchase_date, time(12), tzinfo=ZoneInfo('America/Sao_Paulo'))
    used = select(PurchaseReceipt.cash_transaction_id).where(PurchaseReceipt.cash_transaction_id.is_not(None))
    return [dict(id=str(row.id), description=row.description, amount=str(row.amount), date=row.occurred_at.isoformat()) for row in
        (await session.scalars(select(CashFlowTransaction).where(CashFlowTransaction.transaction_type == CashFlowType.EXPENSE,
            CashFlowTransaction.is_cancelled.is_(False), CashFlowTransaction.amount == amount, CashFlowTransaction.id.not_in(used),
            CashFlowTransaction.occurred_at >= when - timedelta(days=3), CashFlowTransaction.occurred_at <= when + timedelta(days=3)).limit(20))).all()]


@router.post('/receipts', status_code=201)
async def save_receipt(payload: ReceiptInput, session: AsyncSession = Depends(get_session)):
    if not payload.reviewed:
        raise HTTPException(422, 'Revise o cupom e seus produtos antes de salvar.')
    if not payload.supplier_name.strip() or not payload.number.strip() or any(not normalize(item.name) or not normalize(item.unit) for item in payload.items):
        raise HTTPException(422, 'Informe fornecedor, número do cupom, produto e unidade.')
    if payload.create_expense and payload.cash_transaction_id:
        raise HTTPException(422, 'Escolha criar despesa OU vincular uma existente, nunca os dois.')
    if payload.date > datetime.now(ZoneInfo('America/Sao_Paulo')).date() + timedelta(days=1):
        raise HTTPException(422, 'Confira a data do cupom.')
    when = datetime.combine(payload.date, time(12), tzinfo=ZoneInfo('America/Sao_Paulo'))
    # Sum may differ due to discounts, freights and OCR: force explicit correction, not a silent cost error.
    if sum(item.total for item in payload.items) != payload.amount:
        raise HTTPException(422, 'A soma dos itens deve ser igual ao total pago. Distribua descontos/acréscimos nos totais dos itens.')
    keys = [normalize(item.name) + '|' + normalize(item.unit) for item in payload.items]
    if len(set(keys)) != len(keys):
        raise HTTPException(422, 'Agrupe linhas repetidas do mesmo produto/unidade antes de salvar.')
    async with session.begin():
        # Share the bank reconciliation lock: a receipt and a bank import must not create two expenses concurrently.
        await session.execute(text('SELECT pg_advisory_xact_lock(734903)'))
        supplier = await session.get(Supplier, payload.supplier_id) if payload.supplier_id else None
        if payload.supplier_id and not supplier:
            raise HTTPException(404, 'Fornecedor não encontrado.')
        if supplier and payload.cnpj and supplier.cnpj != payload.cnpj:
            raise HTTPException(409, 'CNPJ não corresponde ao fornecedor selecionado.')
        if not supplier:
            if not payload.cnpj:
                raise HTTPException(422, 'Informe o CNPJ para cadastrar o fornecedor ou selecione um fornecedor existente.')
            supplier = await session.scalar(select(Supplier).where(Supplier.identity == payload.cnpj))
            if not supplier:
                supplier = Supplier(name=payload.supplier_name.strip(), identity=payload.cnpj, cnpj=payload.cnpj)
                session.add(supplier); await session.flush()
        fingerprint = hashlib.sha256(f'{supplier.id}|{normalize(payload.number)}|{payload.date}'.encode()).hexdigest()
        checks = [PurchaseReceipt.fingerprint == fingerprint]
        if payload.fiscal_key: checks.append(PurchaseReceipt.fiscal_key == payload.fiscal_key)
        if await session.scalar(select(PurchaseReceipt.id).where(or_(*checks))):
            raise HTTPException(409, 'Cupom já cadastrado. Não foram criados produtos nem despesas novamente.')
        cash = None
        if payload.cash_transaction_id:
            cash = await session.get(CashFlowTransaction, payload.cash_transaction_id)
            used = await session.scalar(select(PurchaseReceipt.id).where(PurchaseReceipt.cash_transaction_id == payload.cash_transaction_id))
            if used or not cash or cash.is_cancelled or cash.transaction_type != CashFlowType.EXPENSE or cash.amount != payload.amount or abs((cash.occurred_at - when).total_seconds()) > 3 * 86400:
                raise HTTPException(409, 'Despesa indisponível ou incompatível com data e valor do cupom.')
        elif payload.create_expense:
            existing = await session.scalar(select(CashFlowTransaction.id).where(CashFlowTransaction.is_cancelled.is_(False),
                CashFlowTransaction.transaction_type == CashFlowType.EXPENSE, CashFlowTransaction.amount == payload.amount,
                CashFlowTransaction.occurred_at >= when - timedelta(days=3), CashFlowTransaction.occurred_at <= when + timedelta(days=3)))
            if existing:
                raise HTTPException(409, f'Possível duplicidade: existe despesa de mesmo valor e data próxima. Salve somente o cupom ou vincule a despesa {existing}.')
            cash = CashFlowTransaction(transaction_type=CashFlowType.EXPENSE, description=f'Cupom {payload.number} — {supplier.name}'[:255],
                category='Compras / revisar', amount=payload.amount, payment_method=payload.payment_method, occurred_at=when,
                notes='Compra por cupom revisado; classificar em Custos e despesas.', classification_reviewed=False)
            session.add(cash); await session.flush()
        changed = 0
        items = []
        for item, identity in zip(payload.items, keys):
            price = (item.total / item.quantity).quantize(Decimal('.0001'))
            if price <= 0 or price > Decimal('9999999999.9999'):
                raise HTTPException(422, 'Preço unitário fora do intervalo suportado. Confira quantidade e unidade.')
            product = await session.scalar(select(SupplierProduct).where(SupplierProduct.supplier_id == supplier.id, SupplierProduct.identity == identity))
            previous = str(product.unit_price) if product else None
            if not product:
                product = SupplierProduct(supplier_id=supplier.id, identity=identity, name=item.name.strip(), unit=item.unit.upper().strip(), unit_price=price, price_date=when)
                session.add(product); changed += 1
            elif when >= product.price_date:
                if product.unit_price != price: changed += 1
                product.unit_price = price; product.price_date = when
            items.append(dict(name=item.name.strip(), unit=item.unit.upper().strip(), quantity=str(item.quantity), total=str(item.total), unit_price=str(price), previous_price=previous))
        receipt = PurchaseReceipt(supplier_id=supplier.id, fingerprint=fingerprint, fiscal_key=payload.fiscal_key or None,
            number=payload.number.strip(), occurred_at=when, amount=payload.amount, items=items, cash_transaction_id=cash.id if cash else None)
        session.add(receipt); await session.flush(); receipt_id = str(receipt.id)
    return dict(id=receipt_id, updated_products=changed, message='Cupom salvo e preços de compra atualizados. Preços de venda e estoque não foram alterados.')
