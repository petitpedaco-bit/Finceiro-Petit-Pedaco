import unittest
import os
import uuid
from decimal import Decimal
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import engine, get_session
from app.main import app
from app.models import Product, CashFlowTransaction
from app.schemas import DiscountType
from app.services.sale_service import allocate_sale_discount, discount


class SaleDiscountTests(unittest.TestCase):
    def test_fixed_and_percentage_totals(self):
        self.assertEqual(discount(Decimal('100'),DiscountType.FIXED,Decimal('10.50')),Decimal('10.50'))
        self.assertEqual(discount(Decimal('90'),DiscountType.PERCENTAGE,Decimal('10')),Decimal('9.00'))

    def test_small_lines_never_receive_a_negative_residual_discount(self):
        values=[Decimal('.01')]*4
        parts=allocate_sale_discount(values,Decimal('.02'))
        self.assertEqual(sum(parts),Decimal('.02'))
        self.assertTrue(all(Decimal('0')<=part<=value for part,value in zip(parts,values)))

    def test_cent_exact_allocation_invariants(self):
        for count in range(1,20):
            values=[Decimal(index+1)/100 for index in range(count)]
            total=sum(values)
            for reduction in (Decimal('0'),Decimal('.01'),(total/2).quantize(Decimal('.01')),total):
                parts=allocate_sale_discount(values,reduction)
                self.assertEqual(sum(parts),reduction)
                self.assertTrue(all(Decimal('0')<=part<=value for part,value in zip(parts,values)))


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Requer PostgreSQL')
class SaleDiscountDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_discount_preview_saved_history_cash_and_stale_price_rejection(self):
        async with engine.connect() as connection:
            outer=await connection.begin()
            def session():return AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
            async def dependency():
                async with session() as db:yield db
            app.dependency_overrides[get_session]=dependency
            try:
                async with session() as db:
                    async with db.begin():
                        product=Product(name='Teste desconto isolado',sku='DISC-'+uuid.uuid4().hex,cost_price=Decimal('5'),additional_cost=0,sale_price=Decimal('50'),current_stock=10)
                        db.add(product);await db.flush();product_id=product.id
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                    cases=[('FIXED','10.50',None,'0','89.50','10.50'),('PERCENTAGE','10',None,'0','90.00','10.00'),('PERCENTAGE','10','PERCENTAGE','10','81.00','19.00')]
                    for kind,value,item_kind,item_value,expected,reduction in cases:
                        payload=dict(payment_method='PIX',items=[dict(product_id=str(product_id),quantity=2,discount_type=item_kind,discount_value=item_value)],sale_discount_type=kind,sale_discount_value=value,expected_net_total=expected)
                        response=await client.post('/sales/checkout',json=payload)
                        self.assertEqual(response.status_code,201,response.text)
                        sale=response.json();self.assertEqual(Decimal(sale['net_total']),Decimal(expected));self.assertEqual(Decimal(sale['discount_total']),Decimal(reduction))
                        self.assertEqual(sum(Decimal(item['line_total']) for item in sale['items']),Decimal(expected))
                        history=(await client.get('/sales/history?limit=100')).json()['items']
                        saved=next(row for row in history if row['id']==sale['id']);self.assertEqual(Decimal(saved['net_total']),Decimal(expected))
                        async with session() as db:
                            cash=await db.scalar(select(CashFlowTransaction).where(CashFlowTransaction.sale_id==uuid.UUID(sale['id'])))
                            self.assertEqual(cash.amount,Decimal(expected))
                        self.assertEqual((await client.delete('/sales/'+sale['id'])).status_code,204)
                    invalid=await client.post('/sales/checkout',json=dict(payment_method='PIX',items=[dict(product_id=str(product_id),quantity=2)],expected_net_total='99.00'))
                    self.assertEqual(invalid.status_code,422)
                async with session() as db:self.assertEqual((await db.get(Product,product_id)).current_stock,10)
            finally:
                app.dependency_overrides.pop(get_session,None);await outer.rollback()
        await engine.dispose()
