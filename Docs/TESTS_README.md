# BridgeOS Test Suite

Comprehensive pytest test suite for the BridgeOS Telegram translation bot.

## Prerequisites

- Python 3.11+
- PostgreSQL (local or Docker)
- The BridgeOS project source code

## Quick Setup

### 1. Create the test database

```bash
# Option A: Local PostgreSQL
createdb bridgeos_test

# Option B: Docker (one-liner)
docker run -d --name bridgeos-test-db \
  -e POSTGRES_DB=bridgeos_test \
  -e POSTGRES_PASSWORD=testpass \
  -p 5432:5432 \
  postgres:16

# If using Docker, set:
export TEST_DATABASE_URL="postgresql://postgres:testpass@localhost:5432/bridgeos_test"
```


### 2. Install dependencies

```bash
pip install pytest pytest-asyncio psycopg2-binary python-telegram-bot anthropic flask google-generativeai typing-extensions
```

### 3. Set environment variable

```bash
# If using local PostgreSQL with defaults:
export TEST_DATABASE_URL="postgresql://localhost/bridgeos_test"

# If using Docker or custom credentials:
export TEST_DATABASE_URL="postgresql://postgres:testpass@localhost:5432/bridgeos_test"
```

### 4. Place the test suite

Copy the `tests/` directory into your BridgeOS project root so the structure is:

```
bridgeos/
├── handlers/
│   ├── __init__.py          # LANGUAGE, GENDER, INDUSTRY = range(3)
│   ├── registration.py
│   ├── commands.py
│   ├── connections.py
│   ├── messages.py
│   ├── tasks.py
│   └── subscriptions.py
├── models/
│   ├── __init__.py
│   ├── user.py
│   ├── manager.py
│   ├── worker.py
│   ├── connection.py
│   ├── message.py
│   ├── task.py
│   ├── subscription.py
│   ├── usage.py
│   └── feedback.py
├── utils/
│   ├── __init__.py
│   ├── db_connection.py
│   ├── translator.py
│   ├── i18n.py
│   ├── helpers.py
│   └── logger.py
├── locales/
│   ├── en.json
│   └── es.json
├── config.py
├── config.json
├── bot.py
├── dashboard.py
├── tests/                  ← TEST SUITE GOES HERE
│   ├── __init__.py
│   ├── test_tier1_models.py
│   ├── test_tier2_webhooks.py
│   ├── test_tier3_handlers.py
│   ├── test_tier3b_edge_cases.py
│   ├── test_tier4_dashboard.py
│   └── test_tier5_i18n.py
├── conftest.py             ← FIXTURES GO HERE (project root)
├── schema.sql              ← DB SCHEMA GOES HERE
└── pytest.ini
```

### 5. Run the tests

```bash
# Run all tests
pytest -v

# Run a specific tier
pytest -v tests/test_tier1_models.py

# Run a specific test class
pytest -v tests/test_tier1_models.py::TestConnectionModel

# Run a single test
pytest -v tests/test_tier1_models.py::TestConnectionModel::test_create_and_get

# Run with output (for debugging)
pytest -v -s
```

## Test Tiers

| Tier | File | What it tests | Count |
|------|------|---------------|-------|
| 1 | `test_tier1_models.py` | Model layer CRUD against real DB | ~45 |
| 2 | `test_tier2_webhooks.py` | Webhook signature verification + subscription lifecycle | ~12 |
| 3 | `test_tier3_handlers.py` | Handler logic with mocked Telegram | ~18 |
| 3b | `test_tier3b_edge_cases.py` | Constraints, capacity, orphans, Unicode | ~16 |
| 4 | `test_tier4_dashboard.py` | Flask auth, CSRF, health, webhook endpoint | ~10 |
| 5 | `test_tier5_i18n.py` | Locale file integrity and consistency | ~7 |

## Architecture Notes

- **Real DB, mocked everything else**: Tests hit PostgreSQL (test database) for all model operations. The Telegram Bot API and LLM translator are mocked.
- **Isolation via TRUNCATE**: Each test starts with clean tables (fast, no schema recreation).
- **Config override**: `load_config()` is monkeypatched to return test-specific settings (free_message_limit=3, enforce_limits=True, testing_mode=False).
- **Mock translator**: Returns `[TRANSLATED:{to_lang}] {original_text}` — deterministic, no API calls.

## Troubleshooting

**"Connection refused"**: PostgreSQL isn't running or TEST_DATABASE_URL is wrong.

**"relation does not exist"**: The schema.sql hasn't been applied. It's auto-applied by the `create_tables` session fixture, but verify the path is correct.

**Import errors**: Make sure the test files are in the right location relative to the project root. The conftest.py adds the project root to sys.path.

**Async test failures**: Install `pytest-asyncio` (`pip install pytest-asyncio`). The `pytest.ini` sets `asyncio_mode = auto`.


**CREATE LOCAL SCHEMA**
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -p 5433 -d bridgeos_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"