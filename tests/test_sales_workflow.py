import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import engine, get_session
from app.main import app
from app.models import BankMovement, CashFlowTransaction, Product, Sale
from app.services.report_service import ReportService


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Requer PostgreSQL')
class SalesWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_checkout_appears_in_history_and_cancellation_reverses_all_once(self):
        async with engine.connect() as connection:
            outer=await connection.begin()
            def session():return AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
            async def dependency():
                async with session() as db:yield db
            app.dependency_overrides[get_session]=dependency
            try:
                async with session() as db:
                    async with db.begin():
                        product=Product(name='Produto teste isolado',sku='TEST-'+uuid.uuid4().hex,cost_price=Decimal('5'),additional_cost=Decimal('2'),sale_price=Decimal('25'),current_stock=10)
                        db.add(product);await db.flush();product_id=product.id;sku=product.sku
                first=date(2000,1,1);last=date(2099,12,31)
                async with session() as db:
                    before=await ReportService(db).get_dre(first,last)
                    cash_before=await ReportService(db).get_cash_flow(first,last)
                    abc_before=await ReportService(db).get_abc_curve(first,last)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                    response=await client.post('/sales/checkout',json={'items':[{'product_id':str(product_id),'quantity':2}],'payment_method':'CREDIT_CARD'})
                    self.assertEqual(response.status_code,201,response.text)
                    sale_id=response.json()['id'];self.assertEqual(Decimal(response.json()['net_total']),Decimal('50.00'))
                    listed=await client.get('/sales/history?limit=100')
                    self.assertEqual(listed.status_code,200,listed.text)
                    history=listed.json();row=next(item for item in history['items'] if item['id']==sale_id)
                    self.assertEqual(row['products'][0]['sku'],sku);self.assertEqual(row['products'][0]['quantity'],2)
                    self.assertFalse(row['is_cancelled'])
                    self.assertIn(sale_id,[item['id'] for item in (await client.get('/sales')).json()])
                    async with session() as db:
                        self.assertEqual((await db.get(Product,product_id)).current_stock,8)
                        current=await ReportService(db).get_dre(first,last)
                        self.assertEqual(current.net_revenue-before.net_revenue,Decimal('50.00'))
                        self.assertEqual(current.cogs-before.cogs,Decimal('14.00'))
                        cash=await db.scalar(select(CashFlowTransaction).where(CashFlowTransaction.sale_id==uuid.UUID(sale_id)))
                        cash_id=cash.id
                        # Conciliação bancária é preservada mesmo ao remover a entrada da venda.
                        db.add(BankMovement(fingerprint=uuid.uuid4().hex*2,account_key='a'*64,statement_hash='b'*64,occurred_at=cash.occurred_at,direction='INCOME',description='Conciliação fictícia',amount=cash.amount,disposition='LINK',cash_transaction_id=cash.id))
                        await db.commit()
                    self.assertEqual((await client.delete(f'/sales/{sale_id}')).status_code,204)
                    self.assertEqual((await client.delete(f'/sales/{sale_id}')).status_code,204)
                    cancelled=(await client.get('/sales/history?state=CANCELLED&limit=100')).json()
                    row=next(item for item in cancelled['items'] if item['id']==sale_id)
                    self.assertTrue(row['is_cancelled']);self.assertIsNotNone(row['cancelled_at'])
                    active=(await client.get('/sales/history?state=ACTIVE&limit=100')).json()
                    self.assertNotIn(sale_id,[item['id'] for item in active['items']])
                    page=(await client.get('/sales/history?limit=1&offset=0')).json()
                    self.assertEqual(page['total'],history['total']);self.assertEqual(len(page['items']),1)
                    self.assertEqual((await client.get('/sales/history?state=INVALID')).status_code,422)
                    self.assertEqual((await client.delete(f'/sales/{uuid.uuid4()}')).status_code,404)
                async with session() as db:
                    product=await db.get(Product,product_id);sale=await db.get(Sale,uuid.UUID(sale_id))
                    self.assertEqual(product.current_stock,10);self.assertTrue(sale.is_cancelled)
                    self.assertIsNone(await db.get(CashFlowTransaction,cash_id))
                    self.assertEqual(await ReportService(db).get_dre(first,last),before)
                    self.assertEqual(await ReportService(db).get_cash_flow(first,last),cash_before)
                    self.assertEqual(await ReportService(db).get_abc_curve(first,last),abc_before)
            finally:
                app.dependency_overrides.pop(get_session,None);await outer.rollback()
        await engine.dispose()
