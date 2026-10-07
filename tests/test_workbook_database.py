"""Integração PostgreSQL; toda a escrita é revertida ao fim do teste."""
import os
import unittest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.database import engine
from app.models import Base, Product, QuotationWorkbook
from app.routers.quotations import SaveWorkbook, quotation_products, save_workbook
from app.services.workbook_service import QuotationBook


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS') == '1', 'Teste requer PostgreSQL')
class WorkbookDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_reload_sync_and_version_conflict(self):
        book = QuotationBook.model_validate({'sheets':[{'name':'Teste DB', 'rows':[
            [{'value':'Custo Matéria-prima'},{},{},{},{'value':10}],
            [{'value':'Custo Embalagem'},{},{},{},{'value':2}],
            [{'value':'Custo fixo p/ Hora'},{},{},{},{'value':3}],
            [{'value':'Custos variáveis'},{},{},{},{'value':1}],
            [{'value':'Margem de Contribuição / Valor de venda'},{},{},{},{'formula':'=SUM(E1:E4)/(100%-E6)'}],
            [{'value':'% Lucro liquido'},{},{},{},{'value':0.36}],
            [{'value':'Rendimento'},{},{},{},{'value':1}],
        ]}]})
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.run_sync(Base.metadata.create_all)
                async with AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as session:
                    payload=SaveWorkbook(title='Teste isolado',book=book,bindings={'Teste DB':'__TEST_QUOTATION__'},sync_sheets=['Teste DB'])
                    result=await save_workbook(payload,session)
                async with AsyncSession(bind=connection,join_transaction_mode='create_savepoint') as session:
                    document=await session.scalar(select(QuotationWorkbook).where(QuotationWorkbook.title=='Teste isolado'))
                    product=await session.scalar(select(Product).where(Product.sku=='__TEST_QUOTATION__'))
                    self.assertEqual(document.version,1)
                    self.assertEqual(float(product.cost_price),10)
                    self.assertEqual(float(product.additional_cost),6)
                    self.assertEqual(float(product.sale_price),25)
                    self.assertEqual(product.current_stock,0)
                    product.current_stock=7
                    await session.commit()
                async with AsyncSession(bind=connection,join_transaction_mode='create_savepoint') as session:
                    matches=await quotation_products(search='__TEST_QUOTATION__',session=session)
                    self.assertEqual(len(matches),1)
                    self.assertTrue(matches[0]['product']['id'])
                    self.assertEqual(matches[0]['product']['sku'],'__TEST_QUOTATION__')
                    self.assertEqual(matches[0]['product']['current_stock'],7)
                    self.assertEqual(matches[0]['product']['additional_cost'],'6.00')
                book.sheets[0].rows[0][4].value=12
                async with AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as session:
                    result=await save_workbook(SaveWorkbook(id=result['id'],version=1,title='Teste isolado',book=book,
                        bindings={'Teste DB':'__TEST_QUOTATION__'},sync_sheets=['Teste DB']),session)
                    self.assertEqual(result['version'],2)
                async with AsyncSession(bind=connection,join_transaction_mode='create_savepoint') as session:
                    product=await session.scalar(select(Product).where(Product.sku=='__TEST_QUOTATION__'))
                    self.assertEqual(float(product.cost_price),12)
                    self.assertEqual(float(product.sale_price),25)
                    self.assertEqual(product.current_stock,7)
                # A new fiche in the next source version creates one product only.
                new_sheet=book.sheets[0].model_copy(deep=True)
                new_sheet.name='Novo produto DB'
                book.sheets.append(new_sheet)
                async with AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as session:
                    result=await save_workbook(SaveWorkbook(id=result['id'],version=2,title='Teste isolado',book=book,
                        bindings={'Teste DB':'__TEST_QUOTATION__','Novo produto DB':'__TEST_NEW_QUOTATION__'},
                        sync_sheets=['Teste DB','Novo produto DB']),session)
                    self.assertEqual(result['created'],1)
                    self.assertEqual(result['updated'],1)
                async with AsyncSession(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as session:
                    result=await save_workbook(SaveWorkbook(id=result['id'],version=3,title='Teste isolado',book=book,
                        bindings=result['bindings'],sync_sheets=['Teste DB','Novo produto DB']),session)
                    self.assertEqual(result['created'],0)
                    self.assertEqual(result['updated'],2)
                async with AsyncSession(bind=connection,join_transaction_mode='create_savepoint') as session:
                    with self.assertRaises(HTTPException) as error:
                        await save_workbook(SaveWorkbook(id=result['id'],version=1,title='Teste isolado',book=book),session)
                    self.assertEqual(error.exception.status_code,409)
            finally:
                await transaction.rollback()
        await engine.dispose()
