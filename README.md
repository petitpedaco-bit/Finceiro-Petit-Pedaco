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

### Cotações vinculadas a produtos

A aba **Cotações** permite ler o Google público ou importar Excel, navegar
pelas abas e editar células na barra de valores/fórmulas. A grade preserva
as posições das células e as fórmulas, incluindo as compartilhadas do Excel.
Use **Recalcular custos** para revisar resultados; marque as fichas de produtos
que deseja sincronizar pelo SKU e clique em **Salvar atualizações no banco**.
A cotação é persistida no PostgreSQL e pode ser reaberta na lista de planilhas.
O controle de versão impede sobrescrever uma edição feita por outra sessão.

O motor calcula operações aritméticas, percentuais, SUM, VLOOKUP exato,
MIN, MAX e ROUND. Fórmulas com erro, referência circular ou funções não
suportadas exibem avisos e resultados vazios. Fichas sem custo ou preço
válidos não podem sincronizar produtos. O editor não reproduz gráficos,
imagens ou toda a formatação visual do Excel. As alterações são salvas no
sistema; não são enviadas de volta ao Google Sheets.

Na tela Produtos, use "Cotações da planilha" para ler o Google Sheets público
ou enviar um Excel `.xlsx`. Revise as fichas reconhecidas e selecione quais aplicar.
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
