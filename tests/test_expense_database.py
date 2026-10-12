import os
import unittest
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.database import engine
from app.models import CashFlowTransaction
from app.schemas import ExpenseCreate, ExpenseClassificationUpdate, ExpenseSuggestionRequest
from app.routers.cash_flow import create_expense, review_classification, suggest_classification, list_expenses
from app.routers.reports import expense_breakdown
from app.services.report_service import ReportService


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Requer PostgreSQL')
class ExpenseDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_classification_preserves_amount_date_reports_and_learns(self):
        async with engine.connect() as connection:
            transaction=await connection.begin()
            def session():return AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
            try:
                async with session() as db:
                    before=await ReportService(db).get_dre(date(2026,10,12),date(2026,10,12))
                async with session() as db:
                    result=await create_expense(ExpenseCreate(description='__Gasto teste isolado__',category='Outros',amount='12.34',payment_method='PIX',payment_date='2026-10-12T12:00:00-03:00'),db)
                import uuid
                identity=uuid.UUID(result['id'])
                async with session() as db:
                    after=await ReportService(db).get_dre(date(2026,10,12),date(2026,10,12))
                    self.assertEqual(after.operating_expenses-before.operating_expenses,Decimal('12.34'))
                    original=await db.get(CashFlowTransaction,identity)
                    original_date=original.occurred_at
                async with session() as db:
                    reviewed=await review_classification(identity,ExpenseClassificationUpdate(category='Produção',expense_nature='INDIRECT_COST',expense_behavior='FIXED',expense_context='PRODUCTION',classification_reviewed=True),db)
                    self.assertEqual(reviewed.amount,Decimal('12.34'))
                    self.assertEqual(reviewed.occurred_at,original_date)
                async with session() as db:
                    current=await ReportService(db).get_dre(date(2026,10,12),date(2026,10,12))
                    self.assertEqual(current.net_profit,after.net_profit)
                    learned=await suggest_classification(ExpenseSuggestionRequest(description='__Gasto teste isolado__',expense_context='PRODUCTION'),db)
                    self.assertEqual(learned['method'],'CONFIRMED_EXAMPLE')
                    general=await suggest_classification(ExpenseSuggestionRequest(description='__Gasto teste isolado__'),db)
                    self.assertEqual(general['expense_nature'],'UNCLASSIFIED')
                    page=await list_expenses(limit=1,offset=0,session=db)
                    self.assertLessEqual(len(page['items']),1)
                    breakdown=await expense_breakdown(date(2026,10,12),date(2026,10,12),db)
                    self.assertEqual(sum(row['amount'] for row in breakdown['groups']),current.operating_expenses)
                async with session() as db:
                    with self.assertRaises(HTTPException):await review_classification(identity,ExpenseClassificationUpdate(category='Outros'),db)
            finally:await transaction.rollback()
        await engine.dispose()
