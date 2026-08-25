from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import CashFlowTransaction, CashFlowType
from app.schemas import ExpenseCreate

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
        )
        session.add(transaction)
        await session.flush()
    return {"id": str(transaction.id), "message": "Despesa registrada com sucesso"}
