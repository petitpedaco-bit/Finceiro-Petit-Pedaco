"""Inicialização explícita do schema para ambientes locais e Docker.

Em produção, prefira substituir este módulo por migrations Alembic versionadas.
"""

import asyncio

from sqlalchemy import text

from app.database import engine
from app.models import Base


async def initialize_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # Compatibilidade para instalações já criadas antes do módulo de custos.
        for statement in (
            "ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'CREDIT_CARD'",
            "ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'DEBIT_CARD'",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS additional_cost NUMERIC(14,2) NOT NULL DEFAULT 0",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS target_margin_percentage NUMERIC(5,2) NOT NULL DEFAULT 0",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS reseller_cash_price NUMERIC(14,2)",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS reseller_card_price NUMERIC(14,2)",
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS payment_fee_rate NUMERIC(6,4) NOT NULL DEFAULT 0",
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS payment_fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0",
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS received_total NUMERIC(14,2)",
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS is_cancelled BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ",
            "UPDATE sales SET received_total = net_total WHERE received_total IS NULL",
            "ALTER TABLE sales ALTER COLUMN received_total SET NOT NULL",
        ):
            await connection.execute(text(statement))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(initialize_database())
