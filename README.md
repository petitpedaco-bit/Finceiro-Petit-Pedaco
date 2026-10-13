# Sistema Financeiro Petit Pedaço

API assíncrona de vendas, estoque e gestão financeira construída com FastAPI,
SQLAlchemy 2.0 e PostgreSQL.

## Executar com Docker

Com Docker Desktop instalado, execute:

```bash
docker compose up --build
```

O sistema web estará disponível em `http://localhost:5173`, a API em
`http://localhost:8000` e a documentação Swagger em `http://localhost:8000/docs`.

O serviço cria as tabelas automaticamente no primeiro início para facilitar o
ambiente local. Para produção, use migrations Alembic versionadas.

## Fluxo de uso

### Classificação automática local

Na aba **Despesas**, a descrição e a finalidade geram sugestões de custo direto,
custo indireto de produção, despesa administrativa, comercial, financeira ou
tributos. Fixo, variável e misto são dimensões independentes. É um motor local
de regras explicáveis e exemplos confirmados, não um serviço de IA generativa.
Não há chave de IA nem envio de descrições a fornecedores de IA. A confirmação
é obrigatória para salvar uma classificação diferente de "Não classificado".
As sugestões não fazem rateios, não alteram fichas, não lançam gastos sozinhas
e não mudam a DRE. Gastos antigos permanecem não classificados até revisão.

O histórico traz 20 registros por página. **Revisar** altera apenas categoria,
classificação, comportamento e finalidade; valor, data e forma de pagamento
são preservados. Descrições iguais, normalizadas e na mesma finalidade usam
as três últimas confirmações como referência; divergências exigem nova revisão.
Nos Relatórios, **Gastos por classificação** agrupa pagamentos, não CMV nem
apropriação contábil. Confira materiais já incluídos nas fichas e taxas geradas
pelo checkout para não lançar saídas duplicadas. Ativos e empréstimos são
sinalizados para revisão, não classificados como despesas automaticamente.

### Carregamento e histórico

A cotação não é carregada na abertura da Visão geral. Produtos usa o resumo
em cache, sem transferir a planilha inteira nem recalculá-la. O resumo antigo
é gerado uma vez e atualizado no salvamento; a busca por SKU também usa esse
cache. A planilha completa é lida em importações e salvamentos explícitos.
A sincronização automática fica restrita à tela Produtos aberta e visível.
Alterar datas de relatórios não recarrega a lista de produtos.
Use **Atualizar dados e histórico** para recarregar os dados; vendas e gastos
também atualizam os relatórios após salvar. A estrutura do banco tem controle
de versão: inicializações seguintes pulam alterações de tabelas e atualizações
de compatibilidade já aplicadas. Novas migrações devem mudar `SCHEMA_VERSION`.

Essas otimizações não eliminam o despertar do plano gratuito do Render após
inatividade: [limitações oficiais](https://render.com/docs/free#spinning-down-on-idle).
Para os testes PostgreSQL, execute primeiro `python -m app.init_db`, depois
`RUN_DATABASE_TESTS=1 python -m unittest discover -s tests` (sintaxe de variável
de ambiente varia conforme o shell). As escritas financeiras de teste são revertidas.

### Cotações vinculadas a produtos

Em **Nova venda**, a lista suspensa mostra todos os produtos cadastrados,
com nome, SKU, preço e estoque. Use o campo **Buscar por nome ou SKU** para
filtrar sem diferenciar acentos ou maiúsculas. Uma correspondência única é
selecionada automaticamente; também é possível selecionar pelo cursor.
Produtos sem estoque são selecionáveis para consulta, mas o botão **Adicionar
à venda** exige saldo disponível. Ajuste em **Produtos → Editar → Estoque atual**.
O botão também bloqueia adições quando todo o estoque já está na venda.

Em **Produtos → Novo produto/Editar**, busque uma ficha salva por SKU ou nome.
Selecione **Usar cotação** para preencher nome, SKU, matéria-prima e custos
adicionais. Produtos novos recebem o preço sugerido; um SKU já cadastrado abre
o produto existente para atualização, preservando preço e estoque. O botão
**Usar preço sugerido** permite mudar o preço explicitamente. O SKU da ficha
selecionada fica protegido para manter o vínculo nas sincronizações futuras.
A busca ignora acentos e caixa, prioriza a versão mais recente de cada SKU e
não consulta o Google. Fichas inválidas não aparecem nos resultados.

A aba **Produtos** mantém o cadastro, a lista e o botão **Novo produto**, e
reúne o painel **Cotação de produtos** abaixo da lista. Não há mais uma aba
Cotações separada nem uma segunda tabela de produtos. O painel conserva
importação Excel/Google, sincronização, avisos de revisão e salvamento no banco.
Não há campo permanente de link nem grade de células. Use **Atualizar do Google
Sheets** para ler a fonte configurada, **Trocar fonte de importação** para mudar
essa fonte, ou **Importar Excel** para enviar um arquivo. A leitura recalcula e
salva todos os produtos válidos; fichas com erros ficam nos avisos de revisão.
O botão **Salvar atualizações no banco** aplica os custos de todas as fichas
válidas. O cadastro busca essas fichas por nome ou SKU. A atualização automática consulta
o Google a cada minuto enquanto a tela Produtos está aberta e visível, sem requisições
simultâneas. Ela pausa com importações não salvas. Não é uma sincronização
instantânea nem um serviço em segundo plano: o plano gratuito pode atrasar a
leitura. Arquivos Excel precisam ser reenviados quando forem alterados.
A cotação é persistida no PostgreSQL e pode ser reaberta na lista de planilhas.
O controle de versão impede sobrescrever uma edição feita por outra sessão.

O motor calcula operações aritméticas, percentuais, SUM, VLOOKUP exato,
MIN, MAX e ROUND. Fórmulas com erro, referência circular ou funções não
suportadas exibem avisos e resultados vazios. Fichas sem custo ou preço
válidos não podem sincronizar produtos. A tabela não reproduz gráficos,
imagens ou toda a formatação visual do Excel. As alterações são salvas no
sistema; não são enviadas de volta ao Google Sheets.

No painel Cotação de produtos da aba Produtos, importe o Google público ou Excel `.xlsx`.
Informe o SKU de um produto existente para atualizá-lo. O SKU sugerido vincula
uma nova ficha por nome de aba; mantenha-o em sincronizações posteriores.
Se a aba for renomeada, informe novamente o SKU do produto existente.

O custo importado separa matéria-prima de custos fixos, embalagem e variáveis.
Taxas de cartão da planilha são excluídas do custo. O preço sugerido vem do
valor de venda sem taxa de cartão. Produtos novos têm estoque zero e os
existentes preservam estoque e preço, salvo seleção explícita para atualizar preços.
As vendas já realizadas preservam os custos gravados no checkout.

O leitor usa resultados calculados salvos no arquivo. Recalcule e salve no
Excel/Google Sheets antes da exportação. Abas sem ficha de custo, como índice,
fornecedores e tabelas de revenda, não geram produtos; valores incompletos
são mostrados como avisos. A atualização é manual pelo botão de leitura.
Para o GitHub Pages, configure a API remota antes de usar a importação.

1. Cadastre produtos em `POST /products`.
2. Registre vendas em `POST /sales/checkout`; estoque e entrada de caixa são
   gravados atomicamente.
3. Registre despesas em `POST /cash-flow/expenses`.
4. Consulte `GET /reports/dre`, `GET /reports/abc-curve` e
   `GET /reports/cash-flow` com `start_date` e `end_date`.

## Importar extratos Nubank

No histórico de custos e despesas, **Cancelar** (ao lado de **Revisar**)
retira a despesa dos cálculos de DRE/lucro, classificação e fluxo de caixa,
incluindo saldos de abertura de períodos seguintes. Requer confirmação.
O lançamento permanece sinalizado como cancelado, com valor/data originais
e data de cancelamento. Não desfaz o pagamento no banco, não mexe em vendas,
produtos ou estoque e não permite cancelar entradas por essa rota.
Cancelamentos repetidos não alteram novamente os valores. Se a despesa veio
de um extrato, o vínculo bancário e a deduplicação são preservados; a
reimportação não recria automaticamente a despesa cancelada.
Rota: `DELETE /cash-flow/expenses/{id}`.

Em **Despesas**, use **Importar extrato PDF — Nubank**. Aceita o PDF digital
original (até 8 MB, 40 páginas, 1.000 movimentações), não fotos ou PDFs com senha.
A prévia confere as movimentações com os totais diários; divergências bloqueiam
o salvamento. Nenhum PDF, CPF ou número de conta é persistido; a conta é
identificada por hash e documentos/contas nas descrições são ocultados.
Nomes de contrapartes e descrições das movimentações selecionadas são mantidos.

O padrão é **somente conferência bancária**, separado da DRE/fluxo operacional.
Entradas não criam vendas, receitas, estoque ou taxas. Pode-se **vincular**
manualmente um lançamento existente do mesmo valor/direção em até três dias,
sem criar um novo valor. As sugestões por valor/data não comprovam correspondência.
Para uma saída ainda não contabilizada, escolha **registrar nova despesa**, revise
categoria/classificação e confirme que não é transferência/aporte/amortização
nem custo ou taxa já registrado. Despesas criadas aparecem no histórico habitual.

Reimportações, inclusive períodos sobrepostos, são deduplicadas por conta, dia,
direção, valor, descrição e ocorrência repetida. Sem identificador bancário,
movimentações idênticas no mesmo dia exigem atenção: extratos parciais desse
mesmo dia podem ser ambíguos. Prefira exportar dias completos. Movimentações
já importadas não são convertidas automaticamente em despesas na reimportação.
O histórico bancário tem paginação e só carrega ao ser aberto. Importação e
despesas são gravadas atomicamente. O horário adotado é meio-dia de São Paulo,
pois este modelo de extrato fornece a data, não a hora de cada transação.

Rotas: `POST /bank-imports/nubank/preview`, `POST /bank-imports/nubank/save`
(multipart, PDF + seleção revisada), `GET /bank-imports/movements`.
A extração usa [pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html),
local no servidor, sem API de IA paga. PagBank não está incluído nesta etapa.

## Executar sem Docker

Configure uma instância PostgreSQL, defina `DATABASE_URL` com o driver
`postgresql+asyncpg`, instale as dependências e inicialize o schema:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL="postgresql+asyncpg://usuario:senha@localhost:5432/financeiro"
python -m app.init_db
uvicorn app.main:app --reload
```
