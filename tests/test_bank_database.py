import os
import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine
from app.models import BankMovement, CashFlowTransaction, CashFlowType, PaymentMethod, Sale
from app.routers.bank_imports import ImportSelection, bank_history, save_selection
from app.services.nubank_service import parse_pages
from app.services.report_service import ReportService
from app.main import app
from app.database import get_session
import httpx
from test_nubank import pdf_bytes, FOOTER


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS') == '1', 'Requer PostgreSQL')
class BankDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_preview_save_reparse_candidates_and_sale_reconciliation(self):
        header=f'Nubank\nConta: {uuid.uuid4().int}-1\nVALORES EM R$\n'
        content=pdf_bytes([header+'09 OUT 2026 Total de entradas + 75,00\nTransferência recebida pelo Pix Cliente\n75,00\nTotal de saídas - 12,34\nTransferência enviada pelo Pix Farinha\n12,34'+FOOTER])
        async with engine.connect() as connection:
            outer=await connection.begin()
            async def dependency():
                async with AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as db:yield db
            app.dependency_overrides[get_session]=dependency
            try:
                async with AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as db:
                    async with db.begin():
                        sale=Sale(gross_total=Decimal('75.00'),net_total=Decimal('75.00'),received_total=Decimal('75.00'),payment_method=PaymentMethod.PIX,created_at=datetime(2026,10,9,15,tzinfo=timezone.utc))
                        db.add(sale);await db.flush()
                        cash=CashFlowTransaction(transaction_type=CashFlowType.INCOME,description='Venda fictícia para conciliação',category='Vendas',amount=Decimal('75.00'),payment_method=PaymentMethod.PIX,occurred_at=datetime(2026,10,9,15,tzinfo=timezone.utc),sale_id=sale.id)
                        db.add(cash);await db.flush();cash_id=cash.id
                async with AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as db:
                    before=await ReportService(db).get_dre(date(2026,10,9),date(2026,10,9))
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                    response=await client.post('/bank-imports/nubank/preview',files={'file':('fake.pdf',content,'application/pdf')})
                    self.assertEqual(response.status_code,200,response.text)
                    preview=response.json();self.assertEqual(len(preview['rows']),2)
                    self.assertNotIn('account_key',preview);self.assertNotIn('statement_hash',preview)
                    self.assertEqual(preview['rows'][1]['suggestion']['expense_nature'],'DIRECT_COST')
                    self.assertFalse(preview['rows'][0]['duplicate'])
                    self.assertTrue(any(item['id']==str(cash_id) and item['is_sale'] for item in preview['rows'][0]['candidates']))
                    # Campos financeiros extras do cliente são ignorados: origem é sempre o PDF relido.
                    selection={'reviewed':True,'rows':[{'fingerprint':preview['rows'][0]['fingerprint'],'action':'LINK','cash_transaction_id':str(cash_id),'amount':'99999.00','direction':'EXPENSE'}]}
                    import json
                    saved=await client.post('/bank-imports/nubank/save',files={'file':('fake.pdf',content,'application/pdf')},data={'selection':json.dumps(selection)})
                    self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(saved.json()['expenses'],0);self.assertEqual(saved.json()['linked'],1)
                    again=await client.post('/bank-imports/nubank/preview',files={'file':('fake.pdf',content,'application/pdf')})
                    self.assertTrue(again.json()['rows'][0]['duplicate'])
                    invalid=await client.post('/bank-imports/nubank/save',files={'file':('fake.pdf',content,'application/pdf')},data={'selection':'{}'})
                    self.assertEqual(invalid.status_code,422)
                    async with AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as db:
                        row=await db.scalar(select(BankMovement).where(BankMovement.fingerprint==preview['rows'][0]['fingerprint']))
                        self.assertEqual(row.amount,Decimal('75.00'));self.assertEqual(row.direction,'INCOME');self.assertEqual(row.cash_transaction_id,cash_id)
                        after=await ReportService(db).get_dre(date(2026,10,9),date(2026,10,9))
                        self.assertEqual(after.net_revenue,before.net_revenue);self.assertEqual(after.net_profit,before.net_profit)
            finally:
                app.dependency_overrides.pop(get_session,None)
                await outer.rollback()
        await engine.dispose()

    async def test_bank_only_expense_link_and_idempotence_preserve_reports(self):
        # Conta aleatória fictícia; tudo fica em uma transação externa revertida ao final.
        header=f'Nubank\nAgência: 0001 Conta: {uuid.uuid4().int}-1\nVALORES EM R$\n'
        parsed=parse_pages([header+'09 OUT 2026 Total de entradas + 75,00\nTransferência recebida pelo Pix Cliente Teste\n75,00\nTotal de saídas - 25,34\nTransferência enviada pelo Pix Farinha Teste\n12,34\nTransferência enviada pelo Pix Aluguel Teste\n13,00'])
        parsed['statement_hash']='a'*64
        incoming, outgoing, existing=parsed['rows']
        async with engine.connect() as connection:
            outer=await connection.begin()
            def session():return AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
            try:
                async with session() as db:
                    before=await ReportService(db).get_dre(date(2026,10,9),date(2026,10,9))
                    before_count=await db.scalar(select(func.count()).select_from(BankMovement))
                async with session() as db:
                    result=await save_selection(parsed,ImportSelection(reviewed=True,rows=[{'fingerprint':incoming['fingerprint']}]),db)
                    self.assertEqual(result['saved'],1);self.assertEqual(result['expenses'],0)
                async with session() as db:
                    after=await ReportService(db).get_dre(date(2026,10,9),date(2026,10,9))
                    self.assertEqual(before.net_profit,after.net_profit)
                    self.assertEqual(before.net_revenue,after.net_revenue)
                async with session() as db:
                    repeated=await save_selection(parsed,ImportSelection(reviewed=True,rows=[{'fingerprint':incoming['fingerprint']}]),db)
                    self.assertEqual(repeated['skipped'],1);self.assertEqual(repeated['saved'],0)
                async with session() as db:
                    result=await save_selection(parsed,ImportSelection(reviewed=True,rows=[{'fingerprint':outgoing['fingerprint'],'action':'EXPENSE','category':'Produção','expense_nature':'DIRECT_COST','expense_behavior':'VARIABLE','expense_context':'PRODUCTION','classification_reviewed':True}]),db)
                    self.assertEqual(result['expenses'],1)
                async with session() as db:
                    after=await ReportService(db).get_dre(date(2026,10,9),date(2026,10,9))
                    self.assertEqual(before.net_profit-after.net_profit,Decimal('12.34'))
                    self.assertEqual(after.net_revenue,before.net_revenue)
                    repeated=await db.scalar(select(BankMovement).where(BankMovement.fingerprint==outgoing['fingerprint']))
                    cash=await db.get(CashFlowTransaction,repeated.cash_transaction_id)
                    self.assertEqual(cash.amount,Decimal('12.34'));self.assertIsNone(cash.sale_id)
                async with session() as db:
                    result=await save_selection(parsed,ImportSelection(reviewed=True,rows=[{'fingerprint':outgoing['fingerprint'],'action':'EXPENSE'}]),db)
                    self.assertEqual(result['expenses'],0);self.assertEqual(result['skipped'],1)
                async with session() as db:
                    async with db.begin():
                        cash=CashFlowTransaction(transaction_type=CashFlowType.EXPENSE,description='Já registrado teste',category='Outros',amount=Decimal('13.00'),payment_method=PaymentMethod.PIX,occurred_at=datetime(2026,10,9,15,tzinfo=timezone.utc))
                        db.add(cash);await db.flush();cash_id=cash.id
                async with session() as db:
                    before_link=await ReportService(db).get_dre(date(2026,10,9),date(2026,10,9))
                async with session() as db:
                    result=await save_selection(parsed,ImportSelection(reviewed=True,rows=[{'fingerprint':existing['fingerprint'],'action':'LINK','cash_transaction_id':str(cash_id)}]),db)
                    self.assertEqual(result['linked'],1);self.assertEqual(result['expenses'],0)
                async with session() as db:
                    after_link=await ReportService(db).get_dre(date(2026,10,9),date(2026,10,9))
                    self.assertEqual(before_link.net_profit,after_link.net_profit)
                    page=await bank_history(limit=1,offset=0,session=db)
                    self.assertEqual(len(page['items']),1);self.assertEqual(page['total'],before_count+3)
            finally:await outer.rollback()
        await engine.dispose()

    async def test_atomic_rejection_income_as_expense_unknown_fingerprint_unreviewed(self):
        header=f'Nubank\nConta: {uuid.uuid4().int}-1\nVALORES EM R$\n'
        parsed=parse_pages([header+'09 OUT 2026 Total de entradas + 50,00\nTransferência recebida pelo Pix Cliente\n50,00\nTotal de saídas - 12,34\nTransferência enviada pelo Pix Farinha\n12,34'])
        parsed['statement_hash']='b'*64
        income,expense=parsed['rows']
        async with engine.connect() as connection:
            outer=await connection.begin()
            def session():return AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
            try:
                cases=[ImportSelection(reviewed=False,rows=[{'fingerprint':income['fingerprint']}]),
                    ImportSelection(reviewed=True,rows=[{'fingerprint':'c'*64}]),
                    ImportSelection(reviewed=True,rows=[{'fingerprint':income['fingerprint']},{'fingerprint':income['fingerprint']}]),
                    ImportSelection(reviewed=True,rows=[{'fingerprint':expense['fingerprint'],'action':'EXPENSE'},{'fingerprint':income['fingerprint'],'action':'EXPENSE'}]),
                    ImportSelection(reviewed=True,rows=[{'fingerprint':expense['fingerprint'],'action':'LINK','cash_transaction_id':str(uuid.uuid4())}])]
                for selection in cases:
                    async with session() as db:
                        with self.assertRaises(HTTPException):await save_selection(parsed,selection,db)
                    async with session() as db:
                        count=await db.scalar(select(func.count()).select_from(BankMovement).where(BankMovement.account_key==parsed['account_key']))
                        self.assertEqual(count,0)
            finally:await outer.rollback()
        await engine.dispose()
