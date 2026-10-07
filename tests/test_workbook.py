import io
import unittest
from openpyxl import Workbook
import httpx

from app.services.google_sheet_service import download_google_sheet
from app.services.workbook_service import QuotationBook, WorkbookCalculator, read_workbook


class GoogleTests(unittest.IsolatedAsyncioTestCase):
    async def test_google_redirect_downloads_file(self):
        def handler(request):
            if request.url.host == 'docs.google.com':
                return httpx.Response(307, headers={'location':'https://doc-test.googleusercontent.com/export'})
            return httpx.Response(200, content=b'PKtest')
        content = await download_google_sheet('https://docs.google.com/spreadsheets/d/abc/edit?usp=sharing', httpx.MockTransport(handler))
        self.assertEqual(content,b'PKtest')

    async def test_redirect_outside_google_is_rejected(self):
        requests = []
        def handler(request):
            requests.append(request.url.host)
            return httpx.Response(307,headers={'location':'http://127.0.0.1/private'})
        with self.assertRaises(ValueError):
            await download_google_sheet('https://docs.google.com/spreadsheets/d/abc/edit',httpx.MockTransport(handler))
        self.assertEqual(requests,['docs.google.com'])


class WorkbookTests(unittest.TestCase):
    def book(self):
        return QuotationBook.model_validate({'sheets':[
            {'name':'Fornecedor','rows':[[{'value':'Farinha'},{'value':1000},{'value':20}],
                [{'value':'Outro'},{'formula':'=B2'},{'formula':'=B2'}]]},
            {'name':'Bolo','rows':[[{'value':'Farinha'},{'value':250},
                {'formula':"=VLOOKUP(A1,'Fornecedor'!A:C,3,FALSE)"},
                {'formula':"=B1*C1/VLOOKUP(A1,'Fornecedor'!A:C,2,FALSE)"}],
                [{'formula':'=SUM(D1)/(100%-40%)'}]]},
        ]})

    def test_recalculates_lookup_cost_and_margin_after_edit(self):
        book = self.book()
        WorkbookCalculator(book).calculate()
        self.assertEqual(book.sheets[1].rows[0][3].value,5)
        book.sheets[1].rows[0][1].value = 500
        WorkbookCalculator(book).calculate()
        self.assertEqual(book.sheets[1].rows[0][3].value,10)
        self.assertAlmostEqual(book.sheets[1].rows[1][0].value,10/.6)

    def test_unknown_formula_does_not_keep_stale_cost(self):
        book = QuotationBook.model_validate({'sheets':[{'name':'Teste','rows':[[{'value':100,'formula':'=UNKNOWN(2)'}]]}]})
        self.assertTrue(WorkbookCalculator(book).calculate())
        self.assertIsNone(book.sheets[0].rows[0][0].value)
        self.assertTrue(book.sheets[0].rows[0][0].error)

    def test_sum_does_not_ignore_spreadsheet_errors(self):
        book = QuotationBook.model_validate({'sheets':[{'name':'Teste','rows':[[{'value':'#REF!'},{'formula':'=SUM(A1)'}]]}]})
        self.assertTrue(WorkbookCalculator(book).calculate())
        self.assertIsNone(book.sheets[0].rows[0][1].value)

    def test_invalid_formulas_become_review_warnings(self):
        for formula in ['="unclosed', '=ROUND("abc",2)']:
            book=QuotationBook.model_validate({'sheets':[{'name':'Teste','rows':[[{'formula':formula}]]}]})
            self.assertTrue(WorkbookCalculator(book).calculate())
            self.assertIsNone(book.sheets[0].rows[0][0].value)

    def test_import_keeps_all_columns_and_formulas(self):
        source=Workbook();sheet=source.active
        sheet['A1']='Receita';sheet['J1']='Embalagem';sheet['O2']='=SUM(A2:B2)'
        sheet['A2']=2;sheet['B2']=3
        buffer=io.BytesIO();source.save(buffer);source.close()
        result=read_workbook(buffer.getvalue())
        self.assertEqual(len(result['sheets'][0]['rows'][0]),15)
        self.assertEqual(result['sheets'][0]['rows'][1][14]['formula'],'=SUM(A2:B2)')
