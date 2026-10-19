"""Conservative OCR suggestions: never invent a total, supplier or product row."""
import re
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models import PurchaseReceipt, Supplier, CashFlowTransaction


def normalize(value: str) -> str:
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c)).split())


def parse_receipt(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cnpj = re.search(r'\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b', text)
    date = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', text)
    total = re.search(r'\b(?:VALOR\s+(?:TOTAL|A\s+PAGAR)|TOTAL(?:\s+A\s+PAGAR)?)\s*[:=]?\s*(?:R\$)?\s*(\d[\d.]*,\d{2})', text, re.I)
    number = re.search(r'\b(?:NFC-?e|COO|CUPOM)\s*(?:N[ºo°.]?\s*)?[:#]?\s*(\d{1,20})', text, re.I)
    key = re.search(r'(?<!\d)(\d{4}(?:\s*\d{4}){10})(?!\d)', text)
    occurred = ''
    if date:
        try: occurred = datetime.strptime(date[1], '%d/%m/%Y').date().isoformat()
        except ValueError: pass
    items = []
    pattern = re.compile(r'^(?:(.*?)\s+)?(\d+(?:[.,]\d{1,4})?)\s*(UN|UND|KG|G|GR|L|LT|ML|PC|PCT|CX)\s*(?:[xX*]\s*)?(\d[\d.]*,\d{2})\s+(\d[\d.]*,\d{2})\s*$', re.I)
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if not match: continue
        name = re.sub(r'^\d+\s+\d+\s+', '', match[1] or '').strip() or (lines[index - 1] if index else '')
        if not name: continue
        items.append(dict(name=name[:160], unit=match[3].upper(), quantity=match[2].replace(',', '.'), total=match[5].replace('.', '').replace(',', '.')))
    return dict(supplier_name=lines[0][:160] if lines else '', cnpj=re.sub(r'\D', '', cnpj[0]) if cnpj else '',
        fiscal_key=re.sub(r'\D', '', key[1]) if key else '', number=number[1] if number else '', date=occurred,
        amount=total[1].replace('.', '').replace(',', '.') if total else '', items=items,
        warnings=['Confira emitente, data, total, quantidades e unidades. A leitura de itens varia por cupom; complete a tabela antes de salvar.'])


async def receipt_candidates(session, row: dict) -> list[dict]:
    return (await receipt_candidates_many(session, [row]))[0]


async def receipt_candidates_many(session, rows: list[dict]) -> list[list[dict]]:
    exits = [row for row in rows if row['direction'] == 'EXPENSE']
    if not exits: return [[] for _ in rows]
    dates = [datetime.fromisoformat(row['occurred_at']) for row in exits]
    records = (await session.execute(select(PurchaseReceipt, Supplier.name, CashFlowTransaction.is_cancelled)
        .join(Supplier).outerjoin(CashFlowTransaction, CashFlowTransaction.id == PurchaseReceipt.cash_transaction_id).where(
        PurchaseReceipt.amount.in_({Decimal(row['amount']) for row in exits}),
        PurchaseReceipt.occurred_at >= min(dates) - timedelta(days=3),
        PurchaseReceipt.occurred_at <= max(dates) + timedelta(days=3)))).all()
    return [[dict(id=str(receipt.id), supplier=name, amount=str(receipt.amount),
        cash_transaction_id=str(receipt.cash_transaction_id) if receipt.cash_transaction_id and not cancelled else None)
        for receipt, name, cancelled in records if row['direction'] == 'EXPENSE' and receipt.amount == Decimal(row['amount'])
        and abs((receipt.occurred_at - datetime.fromisoformat(row['occurred_at'])).total_seconds()) <= 3 * 86400][:20] for row in rows]
