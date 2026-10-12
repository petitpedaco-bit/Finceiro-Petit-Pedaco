"""Sugestões gerenciais locais, explicáveis e sempre sujeitas a revisão."""
import hashlib
import re
import unicodedata
from enum import Enum


class ExpenseNature(str, Enum):
    DIRECT_COST = 'DIRECT_COST'
    INDIRECT_COST = 'INDIRECT_COST'
    ADMINISTRATIVE = 'ADMINISTRATIVE'
    COMMERCIAL = 'COMMERCIAL'
    FINANCIAL = 'FINANCIAL'
    TAX = 'TAX'
    UNCLASSIFIED = 'UNCLASSIFIED'


class ExpenseBehavior(str, Enum):
    FIXED = 'FIXED'
    VARIABLE = 'VARIABLE'
    MIXED = 'MIXED'
    UNSPECIFIED = 'UNSPECIFIED'


class ExpenseContext(str, Enum):
    GENERAL = 'GENERAL'
    PRODUCTION = 'PRODUCTION'
    ADMINISTRATION = 'ADMINISTRATION'
    SALES = 'SALES'


def normalize(value: str) -> str:
    plain = ''.join(c for c in unicodedata.normalize('NFKD',value.casefold()) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+',plain))


def classification_key(description: str) -> str:
    return hashlib.sha256(normalize(description).encode()).hexdigest()


def suggest(description: str, category: str = '', context: str = 'GENERAL', confirmed: list[dict] | None = None) -> dict:
    history=confirmed or []
    if history and len({(r['expense_nature'],r['expense_behavior']) for r in history})==1:
        return {**history[0],'method':'CONFIRMED_EXAMPLE','confidence':'HIGH','reason':'Mesma descrição e finalidade já confirmadas anteriormente. Revise antes de aplicar.'}
    text=normalize(description+' '+category)
    def has(*terms):
        return any(re.search(r'\b'+re.escape(normalize(term))+r'\b',text) for term in terms)
    nature,behavior,category,confidence='UNCLASSIFIED','UNSPECIFIED','Outros / revisar','LOW'
    reason='Informação insuficiente: indique a finalidade e revise a classificação.'
    if (has('compra','aquisição') and has('forno','geladeira','máquina','equipamento')) or has('empréstimo','financiamento'):
        reason='Pode envolver ativo, investimento ou principal de empréstimo. Requer revisão específica; não foi tratado como despesa automaticamente.'
    elif has('taxa de cartão','taxa cartão','tarifa bancária','taxa da maquininha','juros','iof'):
        nature,category,confidence='FINANCIAL','Encargos financeiros','HIGH'
        behavior='VARIABLE' if has('cartão','maquininha') else 'UNSPECIFIED'
        reason='Encargo financeiro. Confira se já foi registrado pelo checkout para evitar duplicidade.'
    elif has('imposto','tributo','icms','iss','pis','cofins','pagamento das','guia das','boleto das','das mei','simples nacional','darf'):
        nature,category,confidence='TAX','Tributos','MEDIUM'
        reason='Tributo identificado. Recuperação e inclusão no custo dependem da finalidade e precisam ser revisadas.'
    elif has('marketing','publicidade','anúncio','comissão de venda','frete de entrega','entrega ao cliente'):
        nature,category,behavior,confidence='COMMERCIAL','Vendas e divulgação','VARIABLE','HIGH'
        reason='Gasto associado à venda, divulgação ou entrega ao cliente.'
    elif has('contador','contabilidade','material de escritório','assinatura de software') or context=='ADMINISTRATION':
        nature,category,confidence='ADMINISTRATIVE','Administração','MEDIUM'
        reason='Finalidade administrativa identificada. Confira a recorrência.'
    elif context=='SALES':
        nature,category,confidence='COMMERCIAL','Vendas e distribuição','MEDIUM'
        reason='Finalidade comercial informada pelo usuário.'
    elif has('farinha','chocolate','leite','ovos','açúcar','manteiga','fermento','cacau','chantilly','ingredientes','matéria prima','embalagens','embalagem do produto','mão de obra direta','confeiteiro'):
        nature,category,behavior,confidence='DIRECT_COST','Insumos e produção','VARIABLE','HIGH'
        reason='Insumo ou trabalho associado aos produtos. Confira se já está incluído na ficha de custo; não foi feito rateio.'
        if has('confeiteiro','mão de obra direta'):behavior,confidence='UNSPECIFIED','MEDIUM'
    elif context=='PRODUCTION' or has('manutenção do forno','manutenção de forno','aluguel da cozinha','gás da cozinha','energia da produção','depreciação'):
        nature,category,confidence='INDIRECT_COST','Estrutura de produção','MEDIUM'
        reason='Estrutura produtiva com possível rateio entre produtos. O sistema não faz apropriação automática.'
    if nature!='UNCLASSIFIED':
        if has('aluguel','assinatura','mensalidade','salário','contador'):behavior='FIXED'
        elif has('energia','água','telefone'):behavior='MIXED'
        elif has('gás','por unidade','por venda','diária'):behavior='VARIABLE'
    if history:confidence,reason='LOW',reason+' Há confirmações anteriores divergentes; revise.'
    return {'expense_nature':nature,'expense_behavior':behavior,'category':category,'method':'LOCAL_RULES','confidence':confidence,'reason':reason}
