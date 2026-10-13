import io
import unittest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from app.services.nubank_service import parse_pages, read_pdf, MAX_PDF_BYTES


HEADER = 'Nubank\nCliente fictício\nCPF: 000.000.000-00 Agência: 0001 Conta: 12345678-9\n09 DE OUTUBRO DE 2026 a 12 DE OUTUBRO DE 2026 VALORES EM R$\n'
FOOTER = '\nTem alguma dúvida? Contato do banco\nExtrato gerado dia 12 de outubro de 2026\n'


def pdf_bytes(pages):
    writer = PdfWriter()
    for content in pages:
        page = writer.add_blank_page(width=595, height=842)
        font = DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),
            NameObject('/BaseFont'):NameObject('/Helvetica'),NameObject('/Encoding'):NameObject('/WinAnsiEncoding')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream = DecodedStreamObject()
        commands = [b'BT /F1 10 Tf 30 800 Td 12 TL']
        for line in content.splitlines():
            data = line.encode('cp1252', errors='replace').replace(b'\\',b'\\\\').replace(b'(',b'\\(').replace(b')',b'\\)')
            commands.append(b'(' + data + b') Tj T*')
        stream.set_data(b'\n'.join(commands)+b'\nET')
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO();writer.write(output);return output.getvalue()


class NubankTests(unittest.TestCase):
    def test_directions_and_verified_totals_not_summary_balance(self):
        result = parse_pages([HEADER+'Saldo final do período\n1.000,00\nTotal de entradas\n800,00\n09 OUT 2026 Total de entradas + 50,00\nTransferência recebida pelo Pix Cliente\nCPF: 123.456.789-00\n50,00\nTotal de saídas - 12,34\nTransferência enviada pelo Pix Farinha\n12,34'+FOOTER])
        self.assertEqual(len(result['rows']),2)
        self.assertEqual(result['income'],'50.00');self.assertEqual(result['expense'],'12.34')
        self.assertNotIn('123.456.789-00',result['rows'][0]['description'])

    def test_inline_amount_description_across_pages_and_identical_occurrences(self):
        pages=[HEADER+'09 OUT 2026 Total de entradas + 100,00\nTransferência recebida pelo Pix Cliente 50,00'+FOOTER,
            HEADER+'Banco fictício Agência: 1 Conta: 1234-5\nTransferência recebida pelo Pix Cliente\nBanco fictício Agência: 1 Conta: 1234-5\n50,00'+FOOTER]
        result=parse_pages(pages)
        self.assertEqual(len(result['rows']),2)
        self.assertNotEqual(result['rows'][0]['fingerprint'],result['rows'][1]['fingerprint'])
        self.assertTrue(any('idênticas' in warning for warning in result['warnings']))
        single=parse_pages([HEADER+'09 OUT 2026 Total de entradas + 50,00\nTransferência recebida pelo Pix Cliente\nBanco fictício Agência: 1 Conta: 1234-5\n50,00'+FOOTER])
        self.assertEqual(single['rows'][0]['fingerprint'],result['rows'][0]['fingerprint'])

    def test_overlap_period_does_not_change_fingerprint_and_account_is_scoped(self):
        content='09 OUT 2026 Total de entradas + 50,00\nTransferência recebida pelo Pix Cliente\n50,00'
        first=parse_pages([HEADER+content+FOOTER])
        second=parse_pages([HEADER.replace('09 DE OUTUBRO','01 DE OUTUBRO')+content+FOOTER])
        self.assertEqual(first['rows'][0]['fingerprint'],second['rows'][0]['fingerprint'])
        other=parse_pages([HEADER.replace('12345678-9','98765432-1')+content+FOOTER])
        self.assertNotEqual(first['rows'][0]['fingerprint'],other['rows'][0]['fingerprint'])

    def test_recipient_nu_pagamentos_is_not_footer_and_day_balances_are_not_transactions(self):
        content='09 OUT 2026 Total de entradas + 50,00\nTransferência recebida pelo Pix Cliente\nNU PAGAMENTOS - IP (0260) Agência: 1 Conta: 123456-7\n50,00\nSaldo do dia 900,00\n10 OUT 2026 Total de saídas - 12,34\nTransferência enviada pelo Pix Fornecedor\n12,34\nSaldo do dia 887,66'
        result=parse_pages([HEADER+content+FOOTER])
        self.assertEqual(len(result['rows']),2)
        self.assertNotIn('Saldo do dia',result['rows'][0]['description'])

    def test_reject_incomplete_unknown_direction_mismatch_and_scan(self):
        cases=[HEADER+'09 OUT 2026 Total de entradas + 50,00\nTransferência recebida pelo Pix Cliente',
            HEADER+'09 OUT 2026 Total de entradas + 50,00\nOperação desconhecida\n50,00',
            HEADER+'09 OUT 2026 Total de entradas + 50,00\nTransferência recebida pelo Pix Cliente\n49,00',
            HEADER+'09 OUT 2026 Total de entradas + 50,00\nTransferência enviada pelo Pix Cliente\n50,00',
            HEADER]
        for content in cases:
            with self.subTest(content=content[-40:]),self.assertRaises(ValueError):parse_pages([content+FOOTER])

    def test_pdf_extraction_and_limits_encrypted_invalid(self):
        pdf=pdf_bytes([HEADER+'09 OUT 2026 Total de saídas - 12,34\nTransferência enviada pelo Pix Farinha\n12,34'+FOOTER])
        self.assertEqual(read_pdf(pdf)['rows'][0]['amount'],'12.34')
        for content in [b'not a pdf',b'%PDF-'+b'x'*MAX_PDF_BYTES,pdf_bytes([HEADER])]:
            with self.assertRaises(ValueError):read_pdf(content)
        writer=PdfWriter();writer.add_blank_page(width=10,height=10);writer.encrypt('secret');output=io.BytesIO();writer.write(output)
        with self.assertRaisesRegex(ValueError,'senha'):read_pdf(output.getvalue())
