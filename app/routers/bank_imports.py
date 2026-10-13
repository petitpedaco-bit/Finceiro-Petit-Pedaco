import json
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import BankMovement, BankMovementEdit, CashFlowTransaction, CashFlowType, PaymentMethod
from app.schemas import ExpenseClassification
from app.services.expense_classifier import classification_key, suggest
from app.services.nubank_service import MAX_PDF_BYTES, read_pdf

router = APIRouter(prefix='/bank-imports', tags=['Extratos Nubank'])


class ImportChoice(ExpenseClassification):
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    action: Literal['BANK_ONLY', 'EXPENSE', 'LINK'] = 'BANK_ONLY'
    cash_transaction_id: uuid.UUID | None = None
    category: str = Field(default='Outros / revisar', min_length=1, max_length=100)
    payment_method: PaymentMethod = PaymentMethod.PIX


class ImportSelection(BaseModel):
    rows: list[ImportChoice] = Field(min_length=1, max_length=1000)
    reviewed: bool = False


class BankEditRequest(ExpenseClassification):
    model_config = {'extra': 'forbid'}
    expected_version: int = Field(ge=1)
    expected_state: str = Field(pattern=r'^[a-f0-9]{64}$')
    action: Literal['BANK_ONLY', 'INCOME', 'EXPENSE', 'LINK']
    cash_transaction_id: uuid.UUID | None = None
    category: str = Field(default='Outros / revisar', min_length=1, max_length=100)
    payment_method: PaymentMethod = PaymentMethod.PIX
    note: str = Field(default='', max_length=500)
    reviewed: bool = False

    @model_validator(mode='after')
    def require_review(self):
        if self.action == 'EXPENSE' and self.expense_nature.value != 'UNCLASSIFIED' and not self.classification_reviewed:
            raise ValueError('Revise a classificação da despesa antes de salvar.')
        return self


def edit_state(bank: BankMovement, cash: CashFlowTransaction | None) -> dict:
    state = dict(version=bank.version, disposition=bank.disposition, note=bank.note or '',
                 cash_id=str(bank.cash_transaction_id) if bank.cash_transaction_id else None)
    state['cash'] = None if cash is None else dict(id=str(cash.id), category=cash.category,
        description=cash.description, amount=str(cash.amount), occurred_at=cash.occurred_at.isoformat(),
        payment_method=cash.payment_method.value, expense_nature=cash.expense_nature,
        expense_behavior=cash.expense_behavior, expense_context=cash.expense_context,
        classification_reviewed=cash.classification_reviewed, is_cancelled=cash.is_cancelled,
        cancelled_at=cash.cancelled_at.isoformat() if cash.cancelled_at else None)
    return state


def state_token(state: dict) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def movement_row(bank: BankMovement) -> dict:
    return dict(occurred_at=bank.occurred_at.isoformat(), direction=bank.direction,
                amount=str(bank.amount), description=bank.description)


def candidate_response(cash: CashFlowTransaction) -> dict:
    return dict(id=str(cash.id), description=cash.description, amount=str(cash.amount),
                occurred_at=cash.occurred_at.isoformat(), is_sale=cash.sale_id is not None)


@router.get('/movements/{movement_id}/edit')
async def get_bank_edit(movement_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    bank = await session.get(BankMovement, movement_id)
    if bank is None:
        raise HTTPException(404, 'Movimentação não encontrada.')
    cash = await session.get(CashFlowTransaction, bank.cash_transaction_id) if bank.cash_transaction_id else None
    state = edit_state(bank, cash)
    candidates = await candidates_for(session, {'rows': [movement_row(bank)]})
    if cash and not cash.is_cancelled and bank.disposition == 'LINK' and matches(movement_row(bank), cash):
        candidates.insert(0, cash)
    return dict(id=str(bank.id), version=bank.version, expected_state=state_token(state),
        **movement_row(bank), disposition=bank.disposition, note=bank.note or '', cash=state['cash'],
        cash_cancelled=bool(cash and cash.is_cancelled), cash_transaction_id=str(bank.cash_transaction_id) if bank.cash_transaction_id else None,
        candidates=[candidate_response(item) for item in candidates if matches(movement_row(bank), item)][:20],
        suggestion=suggest(bank.description, '', 'GENERAL', []) if bank.direction == 'EXPENSE' else None)


@router.patch('/movements/{movement_id}')
async def edit_bank_movement(movement_id: uuid.UUID, payload: BankEditRequest,
                            session: AsyncSession = Depends(get_session)) -> dict:
    if not payload.reviewed:
        raise HTTPException(422, 'Confirme a revisão e o impacto financeiro antes de salvar.')
    async with session.begin():
        await session.execute(text('SELECT pg_advisory_xact_lock(734903)'))
        bank = await session.scalar(select(BankMovement).where(BankMovement.id == movement_id).with_for_update())
        if bank is None:
            raise HTTPException(404, 'Movimentação não encontrada.')
        old = await session.scalar(select(CashFlowTransaction).where(CashFlowTransaction.id == bank.cash_transaction_id).with_for_update()) if bank.cash_transaction_id else None
        before = edit_state(bank, old)
        if bank.version != payload.expected_version or state_token(before) != payload.expected_state:
            raise HTTPException(409, 'Este registro ou lançamento vinculado mudou. Feche a edição e clique em Editar novamente.')
        if payload.action in ('INCOME', 'EXPENSE') and payload.action != bank.direction:
            raise HTTPException(422, 'Entradas podem ser receitas; saídas podem ser despesas. A direção original não pode ser invertida.')
        if not payload.category.strip():
            raise HTTPException(422, 'Informe uma categoria.')
        owned = bank.disposition in ('INCOME', 'EXPENSE') and old is not None
        if owned and (old.sale_id is not None or old.transaction_type.value != bank.direction or old.amount != bank.amount):
            raise HTTPException(409, 'O vínculo financeiro está inconsistente. Não foi alterado.')
        if bank.disposition == 'LINK' and old and not old.is_cancelled and payload.action in ('INCOME', 'EXPENSE'):
            raise HTTPException(409, 'Esta movimentação já está vinculada a um lançamento ativo. Revise esse lançamento para não duplicar valores.')
        target = None
        if payload.action == 'LINK':
            if not payload.cash_transaction_id or owned and payload.cash_transaction_id == old.id:
                raise HTTPException(422, 'Escolha outro lançamento existente para vincular.')
            target = await session.scalar(select(CashFlowTransaction).where(CashFlowTransaction.id == payload.cash_transaction_id).with_for_update())
            used = await session.scalar(select(BankMovement.id).where(
                BankMovement.cash_transaction_id == payload.cash_transaction_id, BankMovement.id != bank.id))
            if not target or used or not matches(movement_row(bank), target):
                raise HTTPException(409, 'O lançamento não está disponível ou não confere com valor, direção e data.')
        keep_owned = owned and not old.is_cancelled and payload.action == bank.disposition
        if owned and not keep_owned and not old.is_cancelled:
            old.is_cancelled = True
            old.cancelled_at = datetime.now(timezone.utc)
        if payload.action in ('INCOME', 'EXPENSE'):
            if keep_owned:
                target = old
            else:
                target = CashFlowTransaction(transaction_type=CashFlowType(payload.action), description=bank.description,
                    amount=bank.amount, occurred_at=bank.occurred_at, payment_method=payload.payment_method,
                    notes='Criado após edição revisada de movimentação Nubank.')
                session.add(target)
            target.category = payload.category.strip()
            target.payment_method = payload.payment_method
            if payload.action == 'EXPENSE':
                target.expense_nature = payload.expense_nature.value
                target.expense_behavior = payload.expense_behavior.value
                target.expense_context = payload.expense_context.value
                target.classification_reviewed = payload.classification_reviewed
                target.classification_key = classification_key(bank.description)
            await session.flush()
        bank.cash_transaction_id = target.id if target else None
        bank.disposition = payload.action
        bank.note = payload.note.strip() or None
        bank.version += 1
        await session.flush()
        session.add(BankMovementEdit(movement_id=bank.id, before=before, after=edit_state(bank, target)))
        version = bank.version
    return dict(id=str(movement_id), version=version, message='Tratamento atualizado. Financeiro recalculado; dados do extrato preservados.')


async def parse_upload(file: UploadFile) -> dict:
    try:
        content = await file.read(MAX_PDF_BYTES + 1)
        return await run_in_threadpool(read_pdf, content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await file.close()


async def candidates_for(session: AsyncSession, parsed: dict) -> list[CashFlowTransaction]:
    dates = [datetime.fromisoformat(row['occurred_at']) for row in parsed['rows']]
    # Busca delimitada: somente valores do extrato e datas próximas; nunca vincula por conta própria.
    linked = select(BankMovement.cash_transaction_id).where(BankMovement.cash_transaction_id.is_not(None))
    return list((await session.scalars(select(CashFlowTransaction).where(
        CashFlowTransaction.is_cancelled.is_(False),
        CashFlowTransaction.occurred_at >= min(dates) - timedelta(days=3),
        CashFlowTransaction.occurred_at <= max(dates) + timedelta(days=3),
        CashFlowTransaction.amount.in_({Decimal(row['amount']) for row in parsed['rows']}),
        CashFlowTransaction.id.not_in(linked),
    ).order_by(CashFlowTransaction.occurred_at, CashFlowTransaction.id).limit(1001))).all())


def matches(row: dict, transaction: CashFlowTransaction) -> bool:
    return (not transaction.is_cancelled and transaction.transaction_type.value == row['direction'] and
            transaction.amount == Decimal(row['amount']) and
            abs((transaction.occurred_at - datetime.fromisoformat(row['occurred_at'])).total_seconds()) <= 3 * 86400)


@router.post('/nubank/preview')
async def preview_nubank(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)) -> dict:
    parsed = await parse_upload(file)
    existing = set((await session.scalars(select(BankMovement.fingerprint).where(
        BankMovement.fingerprint.in_([row['fingerprint'] for row in parsed['rows']])))).all())
    candidates = await candidates_for(session, parsed)
    if len(candidates) > 1000:
        parsed['warnings'].append('Muitos lançamentos candidatos: a lista de sugestões foi limitada. Confira o histórico manualmente.')
    for row in parsed['rows']:
        row['duplicate'] = row['fingerprint'] in existing
        row['suggestion'] = suggest(row['description'], '', 'GENERAL', []) if row['direction'] == 'EXPENSE' else None
        row['candidates'] = [dict(id=str(item.id), description=item.description, amount=str(item.amount),
                                  occurred_at=item.occurred_at.isoformat(), is_sale=item.sale_id is not None)
                             for item in candidates[:1000] if matches(row, item)][:10]
    # Chave da conta e hash do arquivo não são expostos nem editáveis pelo cliente.
    return {key: parsed[key] for key in ('bank', 'rows', 'warnings', 'income', 'expense')}


async def save_selection(parsed: dict, selection: ImportSelection, session: AsyncSession) -> dict:
    if not selection.reviewed:
        raise HTTPException(422, 'Revise e confirme as movimentações antes de salvar.')
    source = {row['fingerprint']: row for row in parsed['rows']}
    if len({row.fingerprint for row in selection.rows}) != len(selection.rows):
        raise HTTPException(422, 'A seleção contém movimentações repetidas.')
    if any(choice.fingerprint not in source for choice in selection.rows):
        raise HTTPException(422, 'A seleção não corresponde ao PDF enviado. Leia novamente o arquivo.')
    saved = skipped = expenses = linked = 0
    async with session.begin():
        await session.execute(text('SELECT pg_advisory_xact_lock(734903)'))
        duplicates = set((await session.scalars(select(BankMovement.fingerprint).where(
            BankMovement.fingerprint.in_([choice.fingerprint for choice in selection.rows])))).all())
        for choice in selection.rows:
            row = source[choice.fingerprint]
            if choice.fingerprint in duplicates:
                skipped += 1
                continue
            cash_id = None
            if choice.action == 'EXPENSE':
                if row['direction'] != 'EXPENSE':
                    raise HTTPException(422, 'Somente saídas podem ser registradas como despesas.')
                if not choice.category.strip():
                    raise HTTPException(422, 'Informe uma categoria para a despesa.')
                expense = CashFlowTransaction(
                    transaction_type=CashFlowType.EXPENSE, description=row['description'],
                    category=choice.category.strip(), amount=Decimal(row['amount']),
                    payment_method=choice.payment_method, occurred_at=datetime.fromisoformat(row['occurred_at']),
                    expense_nature=choice.expense_nature.value, expense_behavior=choice.expense_behavior.value,
                    expense_context=choice.expense_context.value, classification_reviewed=choice.classification_reviewed,
                    classification_key=classification_key(row['description']), notes='Importado de extrato Nubank após revisão manual.')
                session.add(expense)
                await session.flush()
                cash_id = expense.id
                expenses += 1
            elif choice.action == 'LINK':
                if not choice.cash_transaction_id:
                    raise HTTPException(422, 'Escolha o lançamento existente para vincular.')
                candidate = await session.scalar(select(CashFlowTransaction).where(
                    CashFlowTransaction.id == choice.cash_transaction_id).with_for_update())
                already_linked = await session.scalar(select(BankMovement.id).where(
                    BankMovement.cash_transaction_id == choice.cash_transaction_id))
                if not candidate or already_linked or not matches(row, candidate):
                    raise HTTPException(409, 'O lançamento escolhido não está disponível ou não confere com valor, direção e data. Leia novamente o PDF.')
                cash_id = candidate.id
                linked += 1
            session.add(BankMovement(fingerprint=choice.fingerprint, account_key=parsed['account_key'],
                statement_hash=parsed['statement_hash'], occurred_at=datetime.fromisoformat(row['occurred_at']),
                direction=row['direction'], description=row['description'], amount=Decimal(row['amount']),
                disposition=choice.action, cash_transaction_id=cash_id))
            await session.flush()
            saved += 1
    return dict(saved=saved, skipped=skipped, expenses=expenses, linked=linked)


@router.post('/nubank/save')
async def save_nubank(file: UploadFile = File(...), selection: str = Form(..., max_length=600_000),
                      session: AsyncSession = Depends(get_session)) -> dict:
    try:
        payload = ImportSelection.model_validate(json.loads(selection))
    except (ValidationError, ValueError, TypeError) as exc:
        raise HTTPException(422, 'Seleção inválida. Confira as classificações e confirme a revisão dos custos/despesas.') from exc
    # Releitura no servidor: datas, valores e descrições nunca vêm de campos editados no navegador.
    return await save_selection(await parse_upload(file), payload, session)


@router.get('/movements')
async def bank_history(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                       session: AsyncSession = Depends(get_session)) -> dict:
    total = await session.scalar(select(func.count()).select_from(BankMovement))
    rows = (await session.execute(select(BankMovement, CashFlowTransaction.is_cancelled).outerjoin(
        CashFlowTransaction, BankMovement.cash_transaction_id == CashFlowTransaction.id).order_by(BankMovement.occurred_at.desc(),
        BankMovement.created_at.desc(), BankMovement.id.desc()).offset(offset).limit(limit))).all()
    return dict(total=total, items=[dict(id=str(row.id), occurred_at=row.occurred_at.isoformat(),
        direction=row.direction, description=row.description, amount=str(row.amount),
        disposition=row.disposition, cash_cancelled=bool(cancelled),
        version=row.version, note=row.note or '',
        cash_transaction_id=str(row.cash_transaction_id) if row.cash_transaction_id else None) for row, cancelled in rows])
