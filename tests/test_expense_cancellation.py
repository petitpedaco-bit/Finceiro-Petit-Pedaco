import os
import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine, get_session
from app.main import app
from app.models import BankMovement, CashFlowTransaction, CashFlowType, PaymentMethod
from app.routers.bank_imports import ImportSelection, bank_history, candidates_for, matches, save_selection
from app.routers.cash_flow import suggest_classification
from app.routers.reports import expense_breakdown
from app.schemas import ExpenseSuggestionRequest
from app.services.nubank_service import parse_pages
from app.services.report_service import ReportService


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Requer PostgreSQL')
class ExpenseCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_reverses_all_reports_once_preserving_audit_and_bank_dedup(self):
        header=f'Nubank\nConta: {uuid.uuid4().int}-1\nVALORES EM R$\n'
        description='Transferência enviada pelo Pix Teste '+uuid.uuid4().hex
        parsed=parse_pages([header+'07 OUT 2026 Total de saídas - 130,00\n'+description+'\n130,00'])
        parsed['statement_hash']='a'*64
        selection=ImportSelection(reviewed=True,rows=[dict(fingerprint=parsed['rows'][0]['fingerprint'],action='EXPENSE',category='Teste',expense_nature='DIRECT_COST',expense_behavior='VARIABLE',expense_context='PRODUCTION',classification_reviewed=True)])
        day=date(2026,10,7);next_day=date(2026,10,8)
        async with engine.connect() as connection:
            outer=await connection.begin()
            def session():return AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
            async def dependency():
                async with session() as db:yield db
            app.dependency_overrides[get_session]=dependency
            try:
                async with session() as db:
                    before=await ReportService(db).get_dre(day,day)
                    cash_before=await ReportService(db).get_cash_flow(day,day)
                    next_before=await ReportService(db).get_cash_flow(next_day,next_day)
                    abc_before=await ReportService(db).get_abc_curve(day,day)
                async with session() as db:await save_selection(parsed,selection,db)
                async with session() as db:
                    bank=await db.scalar(select(BankMovement).where(BankMovement.fingerprint==parsed['rows'][0]['fingerprint']))
                    identity=bank.cash_transaction_id
                    original=await db.get(CashFlowTransaction,identity)
                    original_date=original.occurred_at
                    active=await ReportService(db).get_dre(day,day)
                    self.assertEqual(active.operating_expenses-before.operating_expenses,Decimal('130.00'))
                    learned=await suggest_classification(ExpenseSuggestionRequest(description=description,expense_context='PRODUCTION'),db)
                    self.assertEqual(learned['method'],'CONFIRMED_EXAMPLE')
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                    response=await client.delete(f'/cash-flow/expenses/{identity}')
                    self.assertEqual(response.status_code,204,response.text)
                    async with session() as db:
                        row=await db.get(CashFlowTransaction,identity);stamp=row.cancelled_at
                        self.assertTrue(row.is_cancelled);self.assertIsNotNone(stamp)
                        self.assertEqual(row.amount,Decimal('130.00'));self.assertEqual(row.occurred_at,original_date)
                    repeated=await client.delete(f'/cash-flow/expenses/{identity}')
                    self.assertEqual(repeated.status_code,204)
                    history=(await client.get('/cash-flow/expenses?limit=100')).json()
                    entry=next(item for item in history['items'] if item['id']==str(identity))
                    self.assertTrue(entry['is_cancelled']);self.assertEqual(Decimal(entry['amount']),Decimal('130.00'))
                    review=await client.patch(f'/cash-flow/expenses/{identity}/classification',json={'category':'Outra','classification_reviewed':True})
                    self.assertEqual(review.status_code,409)
                async with session() as db:
                    row=await db.get(CashFlowTransaction,identity);self.assertEqual(row.cancelled_at,stamp)
                    after=await ReportService(db).get_dre(day,day)
                    self.assertEqual(after,before)
                    self.assertEqual(await ReportService(db).get_cash_flow(day,day),cash_before)
                    self.assertEqual(await ReportService(db).get_cash_flow(next_day,next_day),next_before)
                    self.assertEqual(await ReportService(db).get_abc_curve(day,day),abc_before)
                    breakdown=await expense_breakdown(day,day,db)
                    self.assertEqual(sum((item['amount'] for item in breakdown['groups']),Decimal(0)),before.operating_expenses)
                    learned=await suggest_classification(ExpenseSuggestionRequest(description=description,expense_context='PRODUCTION'),db)
                    self.assertNotEqual(learned['method'],'CONFIRMED_EXAMPLE')
                    self.assertNotIn(identity,[item.id for item in await candidates_for(db,parsed)])
                    self.assertFalse(matches(parsed['rows'][0],row))
                    bank=await db.scalar(select(BankMovement).where(BankMovement.fingerprint==parsed['rows'][0]['fingerprint']))
                    self.assertEqual(bank.cash_transaction_id,identity)
                    history=await bank_history(limit=100,offset=0,session=db)
                    self.assertTrue(next(item for item in history['items'] if item['id']==str(bank.id))['cash_cancelled'])
                async with session() as db:
                    repeated=await save_selection(parsed,selection,db)
                    self.assertEqual(repeated['skipped'],1);self.assertEqual(repeated['expenses'],0)
            finally:
                app.dependency_overrides.pop(get_session,None)
                await outer.rollback()
        await engine.dispose()

    async def test_cancel_cannot_touch_income_unknown_or_invalid_ids(self):
        async with engine.connect() as connection:
            outer=await connection.begin()
            async def dependency():
                async with AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as db:yield db
            app.dependency_overrides[get_session]=dependency
            try:
                async with AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as db:
                    async with db.begin():
                        income=CashFlowTransaction(transaction_type=CashFlowType.INCOME,description='Entrada fictícia',amount=Decimal('7.77'),payment_method=PaymentMethod.PIX,occurred_at=datetime.now(timezone.utc))
                        db.add(income);await db.flush();identity=income.id
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                    self.assertEqual((await client.delete(f'/cash-flow/expenses/{identity}')).status_code,404)
                    self.assertEqual((await client.delete(f'/cash-flow/expenses/{uuid.uuid4()}')).status_code,404)
                    self.assertEqual((await client.delete('/cash-flow/expenses/not-a-uuid')).status_code,422)
                async with AsyncSession(bind=connection,join_transaction_mode='create_savepoint') as db:
                    row=await db.get(CashFlowTransaction,identity)
                    self.assertFalse(row.is_cancelled);self.assertIsNone(row.cancelled_at)
            finally:
                app.dependency_overrides.pop(get_session,None)
                await outer.rollback()
        await engine.dispose()
