import os
import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import engine, get_session
from app.main import app
from app.models import BankMovement, CashFlowTransaction, CashFlowType, PaymentMethod


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Requer PostgreSQL')
class BankFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_filters_apply_before_pagination_search_accents_and_inclusive_local_dates(self):
        async with engine.connect() as connection:
            outer=await connection.begin()
            tag=uuid.uuid4().hex
            def session():return AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
            async def dependency():
                async with session() as db:yield db
            app.dependency_overrides[get_session]=dependency
            try:
                async with session() as db:
                    async with db.begin():
                        cancelled=CashFlowTransaction(transaction_type=CashFlowType.EXPENSE,description='Fictício',amount=Decimal('25'),payment_method=PaymentMethod.PIX,occurred_at=datetime(2026,10,12,15,tzinfo=timezone.utc),is_cancelled=True,cancelled_at=datetime.now(timezone.utc))
                        db.add(cancelled);await db.flush()
                        # 02:59 UTC pertence ao dia anterior em São Paulo; 03:00 UTC já é dia 12.
                        dates=[datetime(2026,10,12,2,59,tzinfo=timezone.utc),datetime(2026,10,12,3,tzinfo=timezone.utc),datetime(2026,10,13,2,59,tzinfo=timezone.utc),datetime(2026,10,13,3,tzinfo=timezone.utc)]
                        for index,stamp in enumerate(dates):
                            db.add(BankMovement(fingerprint=uuid.uuid4().hex*2,account_key='a'*64,statement_hash='b'*64,
                                occurred_at=stamp,direction='EXPENSE' if index==2 else 'INCOME',description=f'{tag} João ação {index}',
                                amount=Decimal('25'),disposition='EXPENSE' if index==2 else 'BANK_ONLY',
                                cash_transaction_id=cancelled.id if index==2 else None,note='Desconto 100% aprovado' if index==1 else ''))
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                    path='/bank-imports/movements'
                    query={'search':tag+' joao acao','start_date':'2026-10-12','end_date':'2026-10-12','limit':1}
                    page=(await client.get(path,params=query)).json()
                    self.assertEqual(page['total'],2);self.assertEqual(len(page['items']),1)
                    second=(await client.get(path,params={**query,'offset':1})).json()
                    self.assertEqual(second['total'],2);self.assertNotEqual(second['items'][0]['id'],page['items'][0]['id'])
                    receipts=(await client.get(path,params={**query,'direction':'INCOME'})).json()
                    self.assertEqual(receipts['total'],1);self.assertEqual(receipts['items'][0]['direction'],'INCOME')
                    expenses=(await client.get(path,params={**query,'treatment':'EXPENSE'})).json()
                    self.assertEqual(expenses['total'],1)
                    canceled=(await client.get(path,params={**query,'treatment':'CANCELLED'})).json()
                    self.assertEqual(canceled['total'],1);self.assertTrue(canceled['items'][0]['cash_cancelled'])
                    notes=(await client.get(path,params={'search':tag+' 100%'})).json()
                    self.assertEqual(notes['total'],1)
                    missing=(await client.get(path,params={'search':tag+' inexistente'})).json()
                    self.assertEqual(missing['total'],0);self.assertEqual(missing['items'],[])
                    for invalid in [{'start_date':'2026-10-13','end_date':'2026-10-12'},{'direction':'OTHER'},{'treatment':'OTHER'},{'start_date':'invalid'},{'search':'x'*151}]:
                        self.assertEqual((await client.get(path,params=invalid)).status_code,422)
            finally:
                app.dependency_overrides.pop(get_session,None);await outer.rollback()
        await engine.dispose()
