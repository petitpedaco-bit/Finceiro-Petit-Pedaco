import unittest
from pydantic import ValidationError
from app.services.expense_classifier import suggest, classification_key
from app.schemas import ExpenseCreate, ExpenseClassificationUpdate


class ExpenseClassifierTests(unittest.TestCase):
    def test_direct_and_indirect_are_not_synonyms_of_variable_and_fixed(self):
        self.assertEqual(suggest('Farinha para bolos')['expense_nature'],'DIRECT_COST')
        self.assertEqual(suggest('Salário do confeiteiro')['expense_behavior'],'FIXED')
        energy=suggest('Conta de energia',context='PRODUCTION')
        self.assertEqual(energy['expense_nature'],'INDIRECT_COST')
        self.assertEqual(energy['expense_behavior'],'MIXED')
        self.assertEqual(suggest('Aluguel da cozinha')['expense_behavior'],'FIXED')

    def test_context_changes_ambiguous_spending(self):
        self.assertEqual(suggest('Conta de energia')['expense_nature'],'UNCLASSIFIED')
        self.assertEqual(suggest('Conta de energia',context='ADMINISTRATION')['expense_nature'],'ADMINISTRATIVE')
        self.assertEqual(suggest('Conta de energia',context='SALES')['expense_nature'],'COMMERCIAL')

    def test_financial_commercial_tax_and_investment_review(self):
        self.assertEqual(suggest('TAXA DE CARTÃO',context='PRODUCTION')['expense_nature'],'FINANCIAL')
        self.assertIn('checkout',suggest('Taxa de cartão')['reason'])
        self.assertEqual(suggest('Publicidade Instagram')['expense_nature'],'COMMERCIAL')
        self.assertEqual(suggest('Pagamento DAS')['expense_nature'],'TAX')
        self.assertEqual(suggest('Compra das embalagens')['expense_nature'],'DIRECT_COST')
        self.assertEqual(suggest('Compra de forno',context='PRODUCTION')['expense_nature'],'UNCLASSIFIED')
        self.assertEqual(suggest('Compra de um forno',context='PRODUCTION')['expense_nature'],'UNCLASSIFIED')
        self.assertEqual(suggest('Pagamento fornecedor')['confidence'],'LOW')

    def test_confirmed_examples_and_conflicts(self):
        examples=[{'expense_nature':'INDIRECT_COST','expense_behavior':'FIXED','category':'Exemplo confirmado'}]
        self.assertEqual(suggest('ABC',confirmed=examples)['method'],'CONFIRMED_EXAMPLE')
        examples.append({'expense_nature':'DIRECT_COST','expense_behavior':'VARIABLE','category':'Outro'})
        result=suggest('Farinha',confirmed=examples)
        self.assertEqual(result['confidence'],'LOW')
        self.assertIn('divergentes',result['reason'])
        self.assertEqual(classification_key(' Conta de ÁGUA! '),classification_key('conta de agua'))

    def test_review_is_required_and_legacy_create_remains_valid(self):
        base={'description':'Farinha','category':'Insumos','amount':'10.00','payment_method':'PIX','payment_date':'2026-10-12T12:00:00-03:00'}
        self.assertEqual(ExpenseCreate(**base).expense_nature.value,'UNCLASSIFIED')
        with self.assertRaises(ValidationError):ExpenseCreate(**base,expense_nature='DIRECT_COST')
        self.assertTrue(ExpenseCreate(**base,expense_nature='DIRECT_COST',classification_reviewed=True).classification_reviewed)
        with self.assertRaises(ValidationError):ExpenseClassificationUpdate(category='   ')
