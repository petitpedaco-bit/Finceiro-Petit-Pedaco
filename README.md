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
o Google a cada minuto enquanto a página está aberta e visível, sem requisições
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
