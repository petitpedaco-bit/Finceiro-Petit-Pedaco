"""Inicialização explícita do schema para ambientes locais e Docker.

Em produção, prefira substituir este módulo por migrations Alembic versionadas.
"""

import asyncio

from sqlalchemy import text

from app.database import engine
from app.models import Base

SCHEMA_VERSION = '2026-10-12-nubank-import-v2'


async def initialize_database() -> None:
    async with engine.begin() as connection:
        await connection.execute(text('SELECT pg_advisory_xact_lock(734902)'))
        await connection.execute(text('CREATE TABLE IF NOT EXISTS app_schema_versions (name VARCHAR(100) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())'))
        applied = await connection.scalar(text('SELECT name FROM app_schema_versions WHERE name=:version'),{'version':SCHEMA_VERSION})
        if applied:
            return
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
            "ALTER TABLE cash_flow_transactions ADD COLUMN IF NOT EXISTS expense_nature VARCHAR(32) NOT NULL DEFAULT 'UNCLASSIFIED'",
            "ALTER TABLE cash_flow_transactions ADD COLUMN IF NOT EXISTS expense_behavior VARCHAR(16) NOT NULL DEFAULT 'UNSPECIFIED'",
            "ALTER TABLE cash_flow_transactions ADD COLUMN IF NOT EXISTS expense_context VARCHAR(24) NOT NULL DEFAULT 'GENERAL'",
            "ALTER TABLE cash_flow_transactions ADD COLUMN IF NOT EXISTS classification_reviewed BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE cash_flow_transactions ADD COLUMN IF NOT EXISTS classification_key VARCHAR(64)",
            "CREATE INDEX IF NOT EXISTS ix_cash_flow_transactions_classification_key ON cash_flow_transactions (classification_key)",
            "ALTER TABLE quotation_workbooks ADD COLUMN IF NOT EXISTS preview_summary JSON",
        ):
            await connection.execute(text(statement))
        await connection.execute(text('INSERT INTO app_schema_versions(name) VALUES (:version)'),{'version':SCHEMA_VERSION})


async def main() -> None:
    try:
        await initialize_database()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
