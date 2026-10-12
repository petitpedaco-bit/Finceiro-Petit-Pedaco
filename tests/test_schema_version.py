import os
import unittest
from sqlalchemy import event
from app.database import engine
from app.init_db import initialize_database


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Requer PostgreSQL inicializado')
class SchemaVersionTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_skips_alterations_and_financial_backfill(self):
        statements=[]
        def capture(conn,cursor,statement,params,context,executemany):statements.append(statement.strip().upper())
        event.listen(engine.sync_engine,'before_cursor_execute',capture)
        try:
            await initialize_database()
            self.assertTrue(any('APP_SCHEMA_VERSIONS' in statement for statement in statements))
            self.assertFalse(any(statement.startswith(('ALTER ','UPDATE ','INSERT ')) for statement in statements))
        finally:
            event.remove(engine.sync_engine,'before_cursor_execute',capture)
            await engine.dispose()
