"""Leitura determinística de extratos digitais Nubank. PDF é dado, nunca instrução."""
import hashlib
import io
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from pypdf import PdfReader

MAX_PDF_BYTES = 8 * 1024 * 1024
MONTHS = dict(zip('JAN FEV MAR ABR MAI JUN JUL AGO SET OUT NOV DEZ'.split(), range(1, 13)))
AMOUNT = r'(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}'
DATE = re.compile(r'^(\d{2})\s+([A-Z]{3})\s+(\d{4})\b', re.I)
TOTAL = re.compile(r'^(?:\d{2}\s+[A-Z]{3}\s+\d{4}\s+)?Total de (entradas|saidas)\s*(.*)$', re.I)
OPERATION = re.compile(r'^(Transferência\s+(?:recebida|enviada)|Reembolso\s+recebido|Pagamento\s+(?:de|da|efetuado)|Compra\s+(?:no|com|em)|Estorno|Depósito|Resgate|Aplicação|Rendimento)', re.I)


def normalized(value: str) -> str:
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c)).split())


def money(value: str) -> Decimal:
    return Decimal(value.replace('.', '').replace(',', '.'))


def redact(value: str) -> str:
    value = re.sub(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11,14}\b', '[documento oculto]', value)
    value = re.sub(r'(?i)(Agência|Conta)\s*:\s*[\d .-]+', r'\1: [oculta]', value)
    return value[:255]


def parse_pages(pages: list[str]) -> dict:
    text = '\n'.join(pages)
    if not re.search(r'(?i)nubank|nu pagamentos', text):
        raise ValueError('Este leitor aceita somente extratos digitais do Nubank.')
    header = pages[0].split('VALORES EM R$')[0]
    account = re.search(r'(?i)Conta\s*:?\s*([\d-]+)', header)
    if not account:
        raise ValueError('Não foi possível identificar a conta no cabeçalho Nubank.')
    account_key = hashlib.sha256(('nubank:' + account.group(1)).encode()).hexdigest()
    rows, totals = [], {}
    current_date = None
    direction = None
    pending_total = None
    details = None
    pending_amount = None
    operation_date = None
    operation_direction = None
    occurrences = Counter()

    def finish():
        nonlocal details, pending_amount
        if details is None:
            return
        if pending_amount is None:
            raise ValueError('Há uma movimentação sem valor. Não importamos extratos incompletos.')
        amount = pending_amount
        if not 0 < amount < Decimal('1000000000000'):
            raise ValueError('Valor de movimentação fora do limite suportado.')
        description = ' '.join(details)
        operation = normalized(details[0])
        if ('enviada' in operation and operation_direction != 'EXPENSE') or ('recebida' in operation and operation_direction != 'INCOME'):
            raise ValueError('Direção da movimentação não confere com o total diário.')
        base = f'{account_key}|{operation_date.date()}|{operation_direction}|{amount:.2f}|{normalized(description)}'
        occurrences[base] += 1
        fingerprint = hashlib.sha256(f'{base}|{occurrences[base]}'.encode()).hexdigest()
        rows.append(dict(fingerprint=fingerprint, occurred_at=operation_date.isoformat(), direction=operation_direction,
                         amount=f'{amount:.2f}', description=redact(description)))
        details = pending_amount = None

    for page in pages:
        # Cabeçalhos e rodapés repetidos nunca entram nas descrições/fingerprints.
        lines = page.splitlines()
        start = next((i + 1 for i, line in enumerate(lines) if 'VALORES EM R$' in line), 0)
        for raw in lines[start:]:
            line = raw.strip()
            if not line:
                continue
            if re.search(r'(?i)^Extrato gerado|^Tem alguma dúvida|^Ouvidoria|^O saldo|^As informações', line):
                break
            date_match = DATE.match(line)
            if date_match:
                finish()
                day, month, year = date_match.groups()
                current_date = datetime(int(year), MONTHS[month.upper()], int(day), 12, tzinfo=ZoneInfo('America/Sao_Paulo'))
            heading = TOTAL.match(normalized(line))
            if heading and current_date:
                finish()
                direction = 'INCOME' if heading.group(1).lower() == 'entradas' else 'EXPENSE'
                pending_total = (current_date.date().isoformat(), direction)
                number = re.search(AMOUNT, heading.group(2))
                if number:
                    totals[pending_total] = money(number.group())
                    pending_total = None
                continue
            if pending_total:
                number = re.fullmatch(r'[-+]?\s*(' + AMOUNT + r')', line)
                if number:
                    totals[pending_total] = money(number.group(1))
                    pending_total = None
                    continue
                if line in ('-', '+'):
                    continue
                raise ValueError('Não foi possível ler um total diário do extrato.')
            if OPERATION.match(line) and current_date and direction:
                finish()
                details = []
                operation_date, operation_direction = current_date, direction
            if details:
                if normalized(line).startswith('saldo do dia'):
                    finish()
                    continue
            if details is not None:
                # Às vezes o valor aparece na primeira linha, mas a descrição continua na página seguinte.
                amount_match = re.search(r'(?<![\d.,])(' + AMOUNT + r')\s*$', line)
                if amount_match:
                    if pending_amount is not None:
                        raise ValueError('Mais de um valor foi encontrado em uma movimentação. Confira o PDF.')
                    pending_amount = money(amount_match.group(1))
                    line = line[:amount_match.start()].strip()
                if line and line not in ('-', '+'):
                    details.append(line)
                    if len(details) > 12:
                        raise ValueError('Descrição de movimentação não reconhecida. Confira o modelo do extrato.')
    finish()
    if pending_total or not rows:
        raise ValueError('Não foi possível ler todas as movimentações. Envie o PDF original exportado pelo Nubank, não uma foto.')
    calculated = defaultdict(Decimal)
    for row in rows:
        calculated[(row['occurred_at'][:10], row['direction'])] += Decimal(row['amount'])
    if not totals or any(calculated[key] != value for key, value in totals.items()) or any(key not in totals for key in calculated):
        raise ValueError('As movimentações lidas não conferem com os totais diários. Nenhum lançamento foi salvo.')
    warnings = ['Entradas e transferências são guardadas para conciliação, sem gerar receita ou venda automaticamente.',
                'Só registre uma saída como despesa se ela ainda não estiver lançada ou incluída em custos/taxas já contabilizados.']
    if any(count > 1 for count in occurrences.values()):
        warnings.append('Há movimentações idênticas no mesmo dia. Revise: sem identificador bancário, a deduplicação considera a quantidade de ocorrências.')
    return dict(bank='Nubank', account_key=account_key, rows=rows, warnings=warnings,
                income=f"{sum((Decimal(row['amount']) for row in rows if row['direction']=='INCOME'), Decimal(0)):.2f}",
                expense=f"{sum((Decimal(row['amount']) for row in rows if row['direction']=='EXPENSE'), Decimal(0)):.2f}")


def read_pdf(content: bytes) -> dict:
    if len(content) > MAX_PDF_BYTES or not content.startswith(b'%PDF-'):
        raise ValueError('Envie um PDF original do Nubank de até 8 MB.')
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError('O PDF está protegido por senha. Exporte uma versão sem senha para importar.')
        if not 1 <= len(reader.pages) <= 40:
            raise ValueError('O extrato deve ter entre 1 e 40 páginas. Exporte um período menor.')
        pages = []
        for page in reader.pages:
            stream = page.get_contents()
            if stream and len(stream.get_data()) > 4 * 1024 * 1024:
                raise ValueError('Uma página é grande demais para leitura segura. Exporte um período menor.')
            pages.append(page.extract_text() or '')
            if sum(map(len, pages)) > 500_000:
                raise ValueError('Extrato muito extenso. Exporte um período menor.')
        result = parse_pages(pages)
        if len(result['rows']) > 1000:
            raise ValueError('Limite de 1.000 movimentações por importação. Exporte um período menor.')
        return {**result, 'statement_hash': hashlib.sha256(content).hexdigest()}
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('PDF inválido ou formato não reconhecido. Envie o extrato original do Nubank.') from exc
