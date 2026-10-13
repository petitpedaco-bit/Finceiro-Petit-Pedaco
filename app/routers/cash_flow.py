import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import CashFlowTransaction, CashFlowType
from app.schemas import ExpenseCreate, ExpenseSuggestionRequest, ExpenseClassificationUpdate, ExpenseResponse
from app.services.expense_classifier import classification_key, suggest

router = APIRouter(prefix="/cash-flow", tags=["Fluxo de Caixa"])


@router.post("/expenses", status_code=status.HTTP_201_CREATED)
async def create_expense(
    payload: ExpenseCreate, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    """Registra uma saída operacional, separada das entradas criadas pelo checkout."""
    async with session.begin():
        transaction = CashFlowTransaction(
            transaction_type=CashFlowType.EXPENSE,
            description=payload.description.strip(),
            category=payload.category.strip(),
            amount=payload.amount,
            payment_method=payload.payment_method,
            occurred_at=payload.payment_date,
            expense_nature=payload.expense_nature.value,
            expense_behavior=payload.expense_behavior.value,
            expense_context=payload.expense_context.value,
            classification_reviewed=payload.classification_reviewed,
            classification_key=classification_key(payload.description),
        )
        session.add(transaction)
        await session.flush()
    return {"id": str(transaction.id), "message": "Despesa registrada com sucesso"}


@router.post('/expenses/suggest')
async def suggest_classification(payload: ExpenseSuggestionRequest, session: AsyncSession = Depends(get_session)) -> dict:
    rows=(await session.scalars(select(CashFlowTransaction).where(
        CashFlowTransaction.transaction_type==CashFlowType.EXPENSE,
        CashFlowTransaction.classification_key==classification_key(payload.description),
        CashFlowTransaction.expense_context==payload.expense_context.value,
        CashFlowTransaction.classification_reviewed.is_(True),
        CashFlowTransaction.is_cancelled.is_(False)
    ).order_by(CashFlowTransaction.created_at.desc(),CashFlowTransaction.id.desc()).limit(3))).all()
    confirmed=[{'expense_nature':row.expense_nature,'expense_behavior':row.expense_behavior,'category':row.category or 'Outros / revisar'} for row in rows]
    return suggest(payload.description,payload.category,payload.expense_context.value,confirmed)


@router.get('/expenses')
async def list_expenses(limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),session:AsyncSession=Depends(get_session)) -> dict:
    condition=CashFlowTransaction.transaction_type==CashFlowType.EXPENSE
    total=await session.scalar(select(func.count()).select_from(CashFlowTransaction).where(condition))
    rows=(await session.scalars(select(CashFlowTransaction).where(condition).order_by(
        CashFlowTransaction.occurred_at.desc(),CashFlowTransaction.id.desc()).offset(offset).limit(limit))).all()
    return {'items':[ExpenseResponse.model_validate(row) for row in rows],'total':total}


@router.patch('/expenses/{expense_id}/classification',response_model=ExpenseResponse)
async def review_classification(expense_id:uuid.UUID,payload:ExpenseClassificationUpdate,session:AsyncSession=Depends(get_session)):
    if not payload.classification_reviewed:
        raise HTTPException(422,'Confirme a revisão antes de atualizar a classificação')
    async with session.begin():
        row=await session.scalar(select(CashFlowTransaction).where(CashFlowTransaction.id==expense_id).with_for_update())
        if row is None or row.transaction_type!=CashFlowType.EXPENSE:
            raise HTTPException(404,'Gasto não encontrado')
        if row.is_cancelled:
            raise HTTPException(409,'Uma despesa cancelada não pode ser revisada.')
        row.category=payload.category.strip()
        row.expense_nature=payload.expense_nature.value
        row.expense_behavior=payload.expense_behavior.value
        row.expense_context=payload.expense_context.value
        row.classification_reviewed=True
        row.classification_key=classification_key(row.description)
        await session.flush()
        result=ExpenseResponse.model_validate(row)
    return result


@router.delete('/expenses/{expense_id}', status_code=status.HTTP_204_NO_CONTENT)
async def cancel_expense(expense_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> None:
    """Cancelamento lógico idempotente; conserva valor, data e vínculo bancário para auditoria."""
    async with session.begin():
        row = await session.scalar(select(CashFlowTransaction).where(
            CashFlowTransaction.id == expense_id).with_for_update())
        if row is None or row.transaction_type != CashFlowType.EXPENSE:
            raise HTTPException(404, 'Despesa não encontrada')
        if not row.is_cancelled:
            row.is_cancelled = True
            row.cancelled_at = datetime.now(timezone.utc)
