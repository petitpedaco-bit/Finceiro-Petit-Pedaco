from fastapi import FastAPI

from app.routers import cash_flow, reports, sales

app = FastAPI(title="Sistema Financeiro e Vendas", version="1.0.0")
app.include_router(sales.router)
app.include_router(reports.router)
app.include_router(cash_flow.router)
