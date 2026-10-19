import os
import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import engine, get_session
from app.main import app
from app.models import SupplierProduct, PurchaseReceipt, CashFlowTransaction
from app.routers.bank_imports import save_selection, ImportSelection
from app.services.receipt_service import parse_receipt, receipt_candidates


class ReceiptParsingTests(unittest.TestCase):
    def test_portuguese_header_and_single_line_items(self):
        parsed=parse_receipt('MERCADO TESTE\nCNPJ 11.222.333/0001-81\n19/10/2026\n001 789123 ACUCAR 2 UN 5,00 10,00\nVALOR TOTAL R$ 10,00')
        self.assertEqual(parsed['cnpj'],'11222333000181')
        self.assertEqual(parsed['date'],'2026-10-19');self.assertEqual(parsed['amount'],'10.00')
        self.assertEqual(parsed['items'],[dict(name='ACUCAR',unit='UN',quantity='2',total='10.00')])

    def test_missing_total_is_not_invented_from_payment_or_change(self):
        parsed=parse_receipt('LOJA\nTroco 50,00\nCartão 100,00\n99/99/9999')
        self.assertEqual(parsed['amount'],'');self.assertEqual(parsed['date'],'');self.assertEqual(parsed['items'],[])

    def test_multiline_items_and_subtotal_does_not_become_total(self):
        parsed=parse_receipt('LOJA\n001 789123 LEITE\n2 UN X 5,00 10,00\nSUBTOTAL 50,00\nTOTAL: R$ 10,00\nNFC-e nº 123')
        self.assertEqual(parsed['amount'],'10.00');self.assertEqual(parsed['number'],'123')
        self.assertEqual(len(parsed['items']),1);self.assertEqual(parsed['items'][0]['quantity'],'2')


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Requer PostgreSQL inicializado')
class ReceiptDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_supplier_prices_duplicates_and_bank_reconciliation(self):
        async with engine.connect() as connection:
            outer=await connection.begin()
            def session(): return AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
            async def dependency():
                async with session() as db: yield db
            app.dependency_overrides[get_session]=dependency
            try:
                cnpj='99'+str(uuid.uuid4().int)[:12]
                payload=dict(supplier_name='Fornecedor fictício',cnpj=cnpj,number='1',date='2026-10-16',amount='10.00',
                    items=[dict(name='Açúcar 1 kg',unit='UN',quantity='2',total='10.00')],reviewed=True,create_expense=True)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                    bad=await client.post('/suppliers/receipts',json={**payload,'reviewed':False});self.assertEqual(bad.status_code,422)
                    result=await client.post('/suppliers/receipts',json=payload);self.assertEqual(result.status_code,201,result.text)
                    receipt_id=result.json()['id']
                    duplicate=await client.post('/suppliers/receipts',json=payload);self.assertEqual(duplicate.status_code,409,duplicate.text)
                    async with session() as db:
                        receipt=await db.get(PurchaseReceipt,uuid.UUID(receipt_id));cash_id=receipt.cash_transaction_id;supplier_id=receipt.supplier_id
                        product=await db.scalar(select(SupplierProduct).where(SupplierProduct.supplier_id==supplier_id))
                        self.assertEqual(product.unit_price,Decimal('5'))
                    # Review accepts a new purchase, preserving prior price and not creating an expense by default.
                    newer={**payload,'number':'2','date':'2026-10-18','create_expense':False,'amount':'12.00',
                        'items':[dict(name='acucar 1 kg',unit='un',quantity='2',total='12.00')]}
                    self.assertEqual((await client.post('/suppliers/receipts',json=newer)).status_code,201)
                    older={**payload,'number':'0','date':'2026-10-15','create_expense':False}
                    self.assertEqual((await client.post('/suppliers/receipts',json=older)).status_code,201)
                    products=(await client.get(f'/suppliers/{supplier_id}/products')).json()
                    self.assertEqual(len(products),1);self.assertEqual(Decimal(products[0]['unit_price']),Decimal('6'))
                    history=(await client.get('/suppliers/receipts/history')).json()
                    item=next(row for row in history['items'] if row['number']=='2' and row['supplier']=='Fornecedor fictício')
                    self.assertEqual(Decimal(item['items'][0]['previous_price']),Decimal('5'))
                    # Different supplier: same name must NOT update the original supplier's product.
                    other={**payload,'cnpj':'98'+cnpj[2:],'create_expense':False}
                    self.assertEqual((await client.post('/suppliers/receipts',json=other)).status_code,201)
                    self.assertEqual(Decimal((await client.get(f'/suppliers/{supplier_id}/products')).json()[0]['unit_price']),Decimal('6'))
                    self.assertEqual((await client.post('/suppliers/receipts',json={**newer,'number':'3','amount':'13.00'})).status_code,422)
                    # Fiscal key duplicates across different declared numbers are still rejected.
                    keyed={**newer,'number':'4','fiscal_key':'1'*44}
                    self.assertEqual((await client.post('/suppliers/receipts',json=keyed)).status_code,201)
                    self.assertEqual((await client.post('/suppliers/receipts',json={**keyed,'number':'5'})).status_code,409)
                row=dict(fingerprint='a'*64,direction='EXPENSE',description='Pagamento fictício',amount='10.00',occurred_at='2026-10-16T15:00:00+00:00')
                parsed=dict(rows=[row],account_key='b'*64,statement_hash='c'*64)
                async with session() as db:
                    candidates=await receipt_candidates(db,row)
                    self.assertIn(str(cash_id),[item['cash_transaction_id'] for item in candidates])
                async with session() as db:
                    with self.assertRaises(Exception) as blocked:
                        await save_selection(parsed,ImportSelection.model_validate(dict(reviewed=True,rows=[dict(fingerprint='a'*64,action='EXPENSE')])),db)
                    self.assertEqual(blocked.exception.status_code,409)
                async with session() as db:
                    result=await save_selection(parsed,ImportSelection.model_validate(dict(reviewed=True,rows=[dict(fingerprint='a'*64,action='LINK',cash_transaction_id=str(cash_id))])),db)
                    self.assertEqual(result['linked'],1);self.assertEqual(result['expenses'],0)
                async with session() as db:
                    self.assertIsNotNone(await db.get(CashFlowTransaction,cash_id))
            finally:
                app.dependency_overrides.pop(get_session,None);await outer.rollback()
        await engine.dispose()
