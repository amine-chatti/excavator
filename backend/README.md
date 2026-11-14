# Backend

## Running the Postgres integration test

From `backend\`, set the connection URL for an available PostgreSQL server and
run the marked test:

```powershell
$env:TEST_POSTGRES_URL = "postgresql+psycopg://user:password@localhost:5432/database"
uv run pytest -m postgres tests\integration\test_postgres.py
```

The test creates and removes a uniquely named temporary schema. The `libpq`
client library must be loadable by `psycopg`.
