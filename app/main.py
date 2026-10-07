from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import cash_flow, products, reports, sales

app = FastAPI(title="Sistema Financeiro e Vendas", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(sales.router)
app.include_router(reports.router)
app.include_router(cash_flow.router)
app.include_router(products.router)
