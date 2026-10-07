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
