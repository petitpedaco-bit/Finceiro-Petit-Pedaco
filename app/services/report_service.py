from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CashFlowTransaction, CashFlowType, Product, Sale, SaleItem
from app.schemas import ABCCurveResponse, ABCProduct, CashFlowResponse, DREResponse

ZERO = Decimal("0.00")


def period_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    if end_date < start_date:
        raise ValueError("end_date não pode ser anterior a start_date")
    start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start, end


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_dre(self, start_date: date, end_date: date) -> DREResponse:
        start, end = period_bounds(start_date, end_date)
        revenue_stmt = select(
            func.coalesce(func.sum(Sale.gross_total), 0).label("gross"),
            func.coalesce(func.sum(Sale.discount_total), 0).label("discounts"),
            func.coalesce(func.sum(Sale.net_total), 0).label("net"),
        ).where(Sale.created_at >= start, Sale.created_at < end)
        revenue = (await self.session.execute(revenue_stmt)).one()

        cogs_stmt = select(func.coalesce(func.sum(SaleItem.unit_cost * SaleItem.quantity), 0)).join(Sale).where(
            Sale.created_at >= start, Sale.created_at < end
        )
        cogs = (await self.session.scalar(cogs_stmt)) or ZERO
        expenses_stmt = select(func.coalesce(func.sum(CashFlowTransaction.amount), 0)).where(
            CashFlowTransaction.transaction_type == CashFlowType.EXPENSE,
            CashFlowTransaction.occurred_at >= start,
            CashFlowTransaction.occurred_at < end,
        )
        expenses = (await self.session.scalar(expenses_stmt)) or ZERO
        gross, discounts, net = Decimal(revenue.gross), Decimal(revenue.discounts), Decimal(revenue.net)
        return DREResponse(
            start_date=start_date, end_date=end_date, gross_revenue=gross,
            deductions_and_discounts=discounts, net_revenue=net, cogs=Decimal(cogs),
            gross_profit=net - Decimal(cogs), operating_expenses=Decimal(expenses),
            net_profit=net - Decimal(cogs) - Decimal(expenses),
        )

    async def get_abc_curve(self, start_date: date, end_date: date) -> ABCCurveResponse:
        start, end = period_bounds(start_date, end_date)
        per_product = (
            select(
                Product.id.label("product_id"), Product.name.label("product_name"),
                func.sum(SaleItem.line_total).label("revenue"),
            )
            .join(SaleItem, SaleItem.product_id == Product.id)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(Sale.created_at >= start, Sale.created_at < end)
            .group_by(Product.id, Product.name)
            .subquery()
        )
        ranked = select(
            per_product.c.product_id, per_product.c.product_name, per_product.c.revenue,
            func.sum(per_product.c.revenue).over().label("total_revenue"),
            func.sum(per_product.c.revenue).over(
                order_by=(per_product.c.revenue.desc(), per_product.c.product_name), rows=(None, 0)
            ).label("cumulative_revenue"),
        ).subquery()
        stmt = select(
            ranked,
            case(
                (ranked.c.cumulative_revenue / func.nullif(ranked.c.total_revenue, 0) <= Decimal("0.80"), "A"),
                (ranked.c.cumulative_revenue / func.nullif(ranked.c.total_revenue, 0) <= Decimal("0.95"), "B"),
                else_="C",
            ).label("classification"),
        ).order_by(ranked.c.revenue.desc(), ranked.c.product_name)
        rows = (await self.session.execute(stmt)).all()
        if not rows:
            return ABCCurveResponse(start_date=start_date, end_date=end_date, total_revenue=ZERO, products=[])
        total = Decimal(rows[0].total_revenue)
        return ABCCurveResponse(
            start_date=start_date, end_date=end_date, total_revenue=total,
            products=[ABCProduct(
                product_id=row.product_id, product_name=row.product_name, revenue=Decimal(row.revenue),
                revenue_percentage=Decimal(row.revenue) / total * 100,
                cumulative_percentage=Decimal(row.cumulative_revenue) / total * 100,
                classification=row.classification,
            ) for row in rows],
        )

    async def get_cash_flow(self, start_date: date, end_date: date) -> CashFlowResponse:
        start, end = period_bounds(start_date, end_date)
        signed_amount = case(
            (CashFlowTransaction.transaction_type == CashFlowType.INCOME, CashFlowTransaction.amount),
            else_=-CashFlowTransaction.amount,
        )
        opening = (await self.session.scalar(select(func.coalesce(func.sum(signed_amount), 0)).where(
            CashFlowTransaction.occurred_at < start
        ))) or ZERO
        amounts = (await self.session.execute(select(
            func.coalesce(func.sum(case((CashFlowTransaction.transaction_type == CashFlowType.INCOME, CashFlowTransaction.amount), else_=0)), 0),
            func.coalesce(func.sum(case((CashFlowTransaction.transaction_type == CashFlowType.EXPENSE, CashFlowTransaction.amount), else_=0)), 0),
        ).where(CashFlowTransaction.occurred_at >= start, CashFlowTransaction.occurred_at < end))).one()
        income, expenses = Decimal(amounts[0]), Decimal(amounts[1])
        return CashFlowResponse(start_date=start_date, end_date=end_date, opening_balance=Decimal(opening), income=income, expenses=expenses, closing_balance=Decimal(opening) + income - expenses)
