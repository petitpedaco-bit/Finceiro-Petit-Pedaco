"""Busca nas fichas válidas de cotações já salvas, sem depender do Google."""
import hashlib
import unicodedata

from app.services.workbook_service import QuotationBook, workbook_quotations


def normalized(value: str) -> str:
    return ''.join(char for char in unicodedata.normalize('NFKD', value.casefold())
                   if not unicodedata.combining(char)).strip()


def search_catalog(documents: list[dict], search: str, limit: int = 20) -> list[dict]:
    # Documents arrive newest first. A SKU always resolves to its latest fiche,
    # even when the name changed and an older document would match the query.
    catalog = {}
    seen = set()
    for document in documents:
        book = QuotationBook.model_validate(document['data'])
        valid = {row['sheet']: row for row in workbook_quotations(book)['rows']}
        for sheet in book.sheets:
            sku = document['bindings'].get(sheet.name,
                'COT-' + hashlib.sha256(sheet.name.encode()).hexdigest()[:16].upper())
            if sku in seen:
                continue
            seen.add(sku)
            if sheet.name in valid:
                catalog[sku] = {**valid[sheet.name], 'sku': sku,
                    'document_id': str(document['id']), 'document_title': document['title']}
    term = normalized(search)
    matches = [row for row in catalog.values()
               if term in normalized(row['sku']) or term in normalized(row['name'])]
    matches.sort(key=lambda row: (
        normalized(row['sku']) != term and normalized(row['name']) != term,
        normalized(row['name']), row['sku']))
    return matches[:limit]
