import os
import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine, get_session
from app.main import app
from app.models import BankMovement, BankMovementEdit, CashFlowTransaction, CashFlowType, PaymentMethod, Sale
from app.routers.bank_imports import ImportSelection, save_selection
from app.services.nubank_service import parse_pages
from app.services.report_service import ReportService


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Requer PostgreSQL')
class BankEditTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection=await engine.connect();self.outer=await self.connection.begin()
        async def dependency():
            async with self.session() as db:yield db
        app.dependency_overrides[get_session]=dependency
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test')
        self.day=date(2026,10,9)

    def session(self):
        return AsyncSession(bind=self.connection,expire_on_commit=False,join_transaction_mode='create_savepoint')

    async def asyncTearDown(self):
        app.dependency_overrides.pop(get_session,None)
        await self.client.aclose();await self.outer.rollback();await self.connection.close();await engine.dispose()

    async def seed(self,direction='INCOME',amount='75,00'):
        header=f'Nubank\nConta: {uuid.uuid4().int}-1\nVALORES EM R$\n'
        operation='Transferência recebida' if direction=='INCOME' else 'Transferência enviada'
        heading='entradas' if direction=='INCOME' else 'saídas'
        parsed=parse_pages([header+f'09 OUT 2026 Total de {heading} {amount}\n{operation} pelo Pix Teste\n{amount}'])
        parsed['statement_hash']='a'*64
        async with self.session() as db:
            await save_selection(parsed,ImportSelection(reviewed=True,rows=[dict(fingerprint=parsed['rows'][0]['fingerprint'])]),db)
        async with self.session() as db:
            bank=await db.scalar(select(BankMovement).where(BankMovement.fingerprint==parsed['rows'][0]['fingerprint']))
            return bank.id,parsed

    async def edit_data(self,identity):
        response=await self.client.get(f'/bank-imports/movements/{identity}/edit')
        self.assertEqual(response.status_code,200,response.text);return response.json()

    def payload(self,data,action,**fields):
        return dict(expected_version=data['version'],expected_state=data['expected_state'],action=action,
                    reviewed=True,category='Categoria teste',**fields)

    async def patch(self,identity,payload,status=200):
        response=await self.client.patch(f'/bank-imports/movements/{identity}',json=payload)
        self.assertEqual(response.status_code,status,response.text);return response

    async def test_revenue_edit_is_unique_reversible_audited_and_does_not_create_sales(self):
        identity,parsed=await self.seed()
        async with self.session() as db:
            before=await ReportService(db).get_dre(self.day,self.day)
            cash_before=await ReportService(db).get_cash_flow(self.day,self.day)
            next_before=await ReportService(db).get_cash_flow(date(2026,10,10),date(2026,10,10))
            sales=await db.scalar(select(func.count()).select_from(Sale))
        original=await self.edit_data(identity)
        await self.patch(identity,self.payload(original,'INCOME',note='Receita confirmada'))
        current=await self.edit_data(identity);cash_id=current['cash']['id']
        await self.patch(identity,self.payload(original,'INCOME'),409)
        await self.patch(identity,self.payload(current,'INCOME',note='Observação corrigida'))
        updated=await self.edit_data(identity)
        self.assertEqual(updated['cash']['id'],cash_id)
        self.assertEqual(updated['amount'],original['amount']);self.assertEqual(updated['description'],original['description'])
        self.assertEqual(updated['occurred_at'],original['occurred_at'])
        async with self.session() as db:
            after=await ReportService(db).get_dre(self.day,self.day)
            self.assertEqual(after.other_income-before.other_income,Decimal('75.00'))
            self.assertEqual(after.net_profit-before.net_profit,Decimal('75.00'))
            self.assertEqual(after.net_revenue,before.net_revenue)
            cash=await ReportService(db).get_cash_flow(self.day,self.day)
            self.assertEqual(cash.income-cash_before.income,Decimal('75.00'))
            self.assertEqual(await db.scalar(select(func.count()).select_from(Sale)),sales)
        await self.patch(identity,self.payload(updated,'BANK_ONLY'))
        async with self.session() as db:
            self.assertEqual(await ReportService(db).get_dre(self.day,self.day),before)
            self.assertEqual(await ReportService(db).get_cash_flow(self.day,self.day),cash_before)
            self.assertEqual(await ReportService(db).get_cash_flow(date(2026,10,10),date(2026,10,10)),next_before)
            cash=await db.get(CashFlowTransaction,uuid.UUID(cash_id));self.assertTrue(cash.is_cancelled)
            self.assertEqual(await db.scalar(select(func.count()).select_from(BankMovementEdit).where(BankMovementEdit.movement_id==identity)),3)
        async with self.session() as db:
            repeated=await save_selection(parsed,ImportSelection(reviewed=True,rows=[dict(fingerprint=parsed['rows'][0]['fingerprint'])]),db)
            self.assertEqual(repeated['skipped'],1)

    async def test_expense_review_stale_cancel_and_explicit_recreation(self):
        identity,_=await self.seed('EXPENSE','25,00')
        async with self.session() as db:before=await ReportService(db).get_dre(self.day,self.day)
        await self.patch(identity,self.payload(await self.edit_data(identity),'EXPENSE',expense_nature='DIRECT_COST',classification_reviewed=True))
        current=await self.edit_data(identity);old_id=current['cash']['id']
        self.assertEqual((await self.client.delete(f'/cash-flow/expenses/{old_id}')).status_code,204)
        await self.patch(identity,self.payload(current,'EXPENSE'),409)
        fresh=await self.edit_data(identity);self.assertTrue(fresh['cash']['is_cancelled'])
        await self.patch(identity,self.payload(fresh,'EXPENSE',note='Novo lançamento revisado'))
        recreated=await self.edit_data(identity);self.assertNotEqual(recreated['cash']['id'],old_id)
        async with self.session() as db:
            self.assertTrue((await db.get(CashFlowTransaction,uuid.UUID(old_id))).is_cancelled)
            current=await ReportService(db).get_dre(self.day,self.day)
            self.assertEqual(current.operating_expenses-before.operating_expenses,Decimal('25.00'))
        await self.patch(identity,self.payload(recreated,'BANK_ONLY',expense_nature='DIRECT_COST',classification_reviewed=False))
        async with self.session() as db:self.assertEqual(await ReportService(db).get_dre(self.day,self.day),before)

    async def test_link_unlink_does_not_cancel_existing_sale_or_duplicate_income(self):
        identity,_=await self.seed()
        async with self.session() as db:
            async with db.begin():
                sale=Sale(gross_total=Decimal('75'),net_total=Decimal('75'),received_total=Decimal('75'),payment_method=PaymentMethod.PIX,created_at=datetime(2026,10,9,15,tzinfo=timezone.utc))
                db.add(sale);await db.flush()
                cash=CashFlowTransaction(transaction_type=CashFlowType.INCOME,description='Venda fictícia',amount=Decimal('75'),payment_method=PaymentMethod.PIX,occurred_at=sale.created_at,sale_id=sale.id)
                db.add(cash);await db.flush();cash_id=cash.id;sale_id=sale.id
        async with self.session() as db:before=await ReportService(db).get_dre(self.day,self.day)
        data=await self.edit_data(identity)
        self.assertIn(str(cash_id),[item['id'] for item in data['candidates']])
        await self.patch(identity,self.payload(data,'LINK',cash_transaction_id=str(cash_id)))
        linked=await self.edit_data(identity)
        await self.patch(identity,self.payload(linked,'INCOME'),409)
        await self.patch(identity,self.payload(linked,'BANK_ONLY'))
        async with self.session() as db:
            self.assertEqual(await ReportService(db).get_dre(self.day,self.day),before)
            self.assertFalse((await db.get(CashFlowTransaction,cash_id)).is_cancelled)
            self.assertFalse((await db.get(Sale,sale_id)).is_cancelled)

    async def test_validation_guards_direction_amount_date_and_unreviewed_changes(self):
        identity,_=await self.seed('EXPENSE','25,00')
        data=await self.edit_data(identity)
        await self.patch(identity,self.payload(data,'INCOME'),422)
        request=self.payload(data,'EXPENSE');request['reviewed']=False
        await self.patch(identity,request,422)
        await self.patch(identity,self.payload(data,'EXPENSE',expense_nature='DIRECT_COST',classification_reviewed=False),422)
        await self.patch(identity,self.payload(data,'EXPENSE',amount='999.00'),422)
        await self.patch(identity,self.payload(data,'BANK_ONLY',occurred_at='2026-01-01T12:00:00Z'),422)
        await self.patch(identity,self.payload(data,'LINK',cash_transaction_id=str(uuid.uuid4())),409)
        self.assertEqual((await self.edit_data(identity))['version'],1)
