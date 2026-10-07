import unittest

from app.services.quotation_catalog import search_catalog


def document(name='Bolo de maçã', sku='BOLO-123', cost=10, identity='latest'):
    return {'id': identity, 'title': 'Cotação', 'bindings': {name: sku}, 'data': {'sheets': [
        {'name': name, 'rows': [
            [{'value': 'Custo Matéria-prima'}, {}, {}, {}, {'value': cost}],
            [{'value': 'Custo Embalagem'}, {}, {}, {}, {'value': 2}],
            [{'value': 'Custo fixo p/ Hora'}, {}, {}, {}, {'value': 3}],
            [{'value': 'Custos variáveis'}, {}, {}, {}, {'value': 1}],
            [{'value': 'Margem de Contribuição / Valor de venda'}, {}, {}, {}, {'value': 25}],
            [{'value': '% Lucro liquido'}, {}, {}, {}, {'value': 0.36}],
            [{'value': 'Rendimento'}, {}, {}, {}, {'value': 1}],
        ]} ]}}


class QuotationCatalogTests(unittest.TestCase):
    def test_search_by_bound_sku_or_name_ignores_case_accents(self):
        for term in ['bolo-123', ' BOLO-123 ', 'MACA', 'bolo de maçã']:
            rows=search_catalog([document()], term)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['sku'],'BOLO-123')
            self.assertEqual(rows[0]['cost_price'],'10.00')
            self.assertEqual(rows[0]['additional_cost'],'6.00')

    def test_latest_fiche_wins_and_old_name_does_not_match(self):
        docs=[document(name='Bolo novo',cost=12),document(name='Bolo antigo',identity='old')]
        self.assertEqual(search_catalog(docs,'antigo'),[])
        rows=search_catalog(docs,'BOLO-123')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['cost_price'],'12.00')

    def test_invalid_fiche_is_not_available_for_registration(self):
        self.assertEqual(search_catalog([document(cost='#REF!')],''),[])
        self.assertEqual(search_catalog([document(cost='#REF!'),document(identity='old')],''),[])

    def test_exact_match_first_and_result_limit(self):
        docs=[document(name='Bolo abacaxi',sku='OUTRO'),document(name='Bolo',sku='EXATO')]
        self.assertEqual(search_catalog(docs,'bolo',limit=1)[0]['sku'],'EXATO')
        self.assertEqual(search_catalog(docs,'inexistente'),[])
