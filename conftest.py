"""
conftest.py — Shared pytest fixtures for BridgeOS test suite.

Setup:
    1. Install: pip install pytest psycopg2-binary python-telegram-bot anthropic flask
    2. Create a local test database:
         createdb bridgeos_test
    3. Set env var:
         export TEST_DATABASE_URL="postgresql://localhost/bridgeos_test"
    4. Run:
         pytest -v

The fixtures handle:
    - Initializing the connection pool pointed at the test DB
    - Creating tables from schema.sql
    - Truncating all tables between tests (fast isolation)
    - Providing factory functions for common entities (users, managers, workers, connections)
    - Mocking external services (translator, Telegram Bot API)
"""
import os
import sys
import json
import pytest
import psycopg2

# ---------------------------------------------------------------------------
# Path setup: make the project root importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Environment overrides — MUST happen before any project imports
# ---------------------------------------------------------------------------

# Point the connection pool at the test database
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://localhost/bridgeos_test"
)
os.environ["DATABASE_URL"] = TEST_DB_URL

# Provide dummy tokens/keys so config.py doesn't crash
os.environ.setdefault("TELEGRAM_TOKEN", "000000000:TEST_TOKEN_NOT_REAL")
os.environ.setdefault("CLAUDE_API_KEY", "sk-test-not-real")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("LEMONSQUEEZY_WEBHOOK_SECRET", "test_webhook_secret_123")
os.environ.setdefault("DASHBOARD_PASSWORD", "test_password")
os.environ.setdefault("BOT_ID", "bot1")

# Ensure all 5 bot tokens exist for helpers.py
for slot in range(1, 6):
    os.environ.setdefault(f"TELEGRAM_TOKEN_BOT{slot}", f"000000000:TEST_TOKEN_BOT{slot}")


# ---------------------------------------------------------------------------
# Schema path
# ---------------------------------------------------------------------------
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


# ---------------------------------------------------------------------------
# Session-scoped: create tables once per test run
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """
    Create all tables in the test database at the start of the test run.
    Uses a direct psycopg2 connection (not the pool) to avoid circular deps.
    """
    conn = psycopg2.connect(TEST_DB_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Read and execute schema
    with open(SCHEMA_PATH, "r") as f:
        schema_sql = f.read()
    cur.execute(schema_sql)

    cur.close()
    conn.close()
    yield
    # Tables persist across the run — teardown is just truncation per test


@pytest.fixture(scope="session", autouse=True)
def init_pool(create_tables):
    """
    Initialize the global connection pool once per test run,
    pointed at the test database.
    """
    from utils.db_connection import init_connection_pool, close_all_connections, _connection_pool

    # Force re-init if leftover from a previous run
    import utils.db_connection as db_mod
    if db_mod._connection_pool is not None:
        db_mod._connection_pool = None

    init_connection_pool(min_conn=2, max_conn=10)
    yield
    close_all_connections()


# ---------------------------------------------------------------------------
# Per-test: truncate all tables for isolation
# ---------------------------------------------------------------------------

# Order matters: children first (FK constraints)
TABLES_IN_TRUNCATION_ORDER = [
    "feedback",
    "usage_tracking",
    "subscriptions",
    "tasks",
    "messages",
    "connections",
    "workers",
    "managers",
    "users",
]


@pytest.fixture(autouse=True)
def clean_tables():
    """
    Truncate every table before each test.
    CASCADE handles FK dependencies.
    """
    from utils.db_connection import get_db_cursor

    with get_db_cursor() as cur:
        for table in TABLES_IN_TRUNCATION_ORDER:
            cur.execute(f"TRUNCATE TABLE {table} CASCADE")
    yield


# ---------------------------------------------------------------------------
# Test config override: enforce limits, low free tier, no testing_mode bypass
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def override_config(monkeypatch):
    """
    Patch load_config() to return a controlled test configuration.
    - free_message_limit=3 (easy to hit in tests)
    - enforce_limits=True
    - testing_mode=False (don't bypass limits for test_user_ids)
    """
    test_config = {
        "telegram_token": "000000000:TEST_TOKEN_NOT_REAL",
        "admin_telegram_id": "999999",
        "translation_context_size": 3,
        "message_retention_days": 30,
        "free_message_limit": 3,
        "enforce_limits": True,
        "testing_mode": False,
        "test_user_ids": [],
        "languages": [
            "English", "עברית", "العربية", "ไทย", "Español",
            "Türkçe", "Français", "Deutsch", "Português",
            "Русский", "हिन्दी", "Filipino"
        ],
        "language_mapping": {
            "English": "en", "עברית": "he", "العربية": "ar",
            "ไทย": "th", "Español": "es", "Türkçe": "tr",
            "Français": "fr", "Deutsch": "de", "Português": "pt",
            "Русский": "ru", "हिन्दी": "hi", "Filipino": "tl"
        },
        "industries": {
            "dairy_farm": {
                "name": "Dairy Farm",
                "description": "Dairy farm operations."
            },
            "construction": {
                "name": "Construction",
                "description": "Construction site operations."
            },
            "other": {
                "name": "General Workplace",
                "description": "General workplace communication."
            }
        },
        "translation_provider": "claude",
        "claude": {
            "api_key": "sk-test-not-real",
            "model": "claude-sonnet-4-20250514"
        },
        "gemini": {"api_key": "", "model": "gemini-2.5-flash-lite"},
        "openai": {"api_key": "", "model": "gpt-4o-mini"},
        "lemonsqueezy": {
            "store_url": "bridgeos.lemonsqueezy.com",
            "checkout_id": "test-checkout-id",
            "monthly_price": 9.00,
            "webhook_secret": "test_webhook_secret_123",
        },
    }

    import config as config_mod
    monkeypatch.setattr(config_mod, "load_config", lambda: test_config)


# ---------------------------------------------------------------------------
# Factory fixtures — quick creation of common entities
# ---------------------------------------------------------------------------

@pytest.fixture
def make_user():
    """
    Factory fixture: create a user in the DB and return its dict.
    Usage: user = make_user(1001, "Alice", "English", "Female")
    """
    import models.user as user_model

    def _make(user_id=1001, name="TestUser", language="English", gender="Male"):
        user_model.create(user_id, telegram_name=name, language=language, gender=gender)
        return user_model.get_by_id(user_id)

    return _make


@pytest.fixture
def make_manager(make_user):
    """
    Factory fixture: create a user + manager record.
    Returns (user_dict, manager_dict).
    """
    import models.manager as manager_model

    def _make(user_id=1001, name="ManagerUser", language="English",
              gender="Male", code="BRIDGE-10001", industry="dairy_farm"):
        user = make_user(user_id, name, language, gender)
        manager_model.create(user_id, code, industry)
        mgr = manager_model.get_by_id(user_id)
        return user, mgr

    return _make


@pytest.fixture
def make_worker(make_user):
    """
    Factory fixture: create a user + worker record.
    Returns (user_dict, worker_dict).
    """
    import models.worker as worker_model

    def _make(user_id=2001, name="WorkerUser", language="Español",
              gender="Female"):
        user = make_user(user_id, name, language, gender)
        worker_model.create(user_id)
        wrk = worker_model.get_by_id(user_id)
        return user, wrk

    return _make


@pytest.fixture
def make_connection(make_manager, make_worker):
    """
    Factory fixture: create a manager, worker, and connection between them.
    Returns (manager_user, worker_user, connection_dict).
    """
    import models.connection as connection_model

    def _make(manager_id=1001, worker_id=2001, bot_slot=1,
              manager_lang="English", worker_lang="Español",
              code="BRIDGE-10001", industry="dairy_farm"):
        m_user, m_mgr = make_manager(
            manager_id, f"Manager{manager_id}", manager_lang, "Male", code, industry)
        w_user, w_wrk = make_worker(
            worker_id, f"Worker{worker_id}", worker_lang, "Female")
        conn_id = connection_model.create(manager_id, worker_id, bot_slot)
        conn = connection_model.get_by_id(conn_id)
        return m_user, w_user, conn

    return _make


# ---------------------------------------------------------------------------
# Mock translator — never call real LLM APIs
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_translator(monkeypatch):
    """
    Replace the translate() function with a deterministic mock.
    Returns "[TRANSLATED:{to_lang}] {original_text}" so tests can assert
    on the shape of the output without hitting an API.
    """
    def fake_translate(text, from_lang, to_lang, target_gender=None,
                       conversation_history=None, industry=None):
        return f"[TRANSLATED:{to_lang}] {text}"

    def fake_daily(messages, industry=None, manager_language=None):
        count = len(messages) if messages else 0
        return f"Action items from {count} messages"

    import utils.translator as translator_mod
    monkeypatch.setattr(translator_mod, "translate", fake_translate)
    monkeypatch.setattr(translator_mod, "generate_daily_actionitems", fake_daily)


# ---------------------------------------------------------------------------
# Telegram mock helpers (for handler tests)
# ---------------------------------------------------------------------------

class MockBot:
    """Minimal mock of telegram.Bot for handler tests."""
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.sent_messages.append({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
        })

    async def get_chat(self, chat_id):
        return type("Chat", (), {"first_name": f"User{chat_id}", "id": chat_id})()


class MockMessage:
    """Minimal mock of telegram.Message."""
    def __init__(self, text="", chat_id=0, user_id=0, first_name="Test"):
        self.text = text
        self.chat = type("Chat", (), {"id": chat_id})()
        self.message_id = 1
        self._replies = []
        self._forwards = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None):
        self._replies.append({
            "text": text,
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
        })
        return self

    async def forward(self, chat_id):
        self._forwards.append(chat_id)

    async def delete(self):
        pass

class MockUser:
    """Minimal mock of telegram.User."""
    def __init__(self, user_id=0, first_name="Test", username="testuser"):
        self.id = user_id
        self.first_name = first_name
        self.username = username


class MockUpdate:
    """
    Minimal mock of telegram.Update for handler tests.
    Supports both message-based and callback_query-based updates.
    """
    def __init__(self, user_id=0, text="", first_name="Test", username="testuser",
                 callback_data=None):
        self.effective_user = MockUser(user_id, first_name, username)
        self.message = MockMessage(text=text, chat_id=user_id, user_id=user_id,
                                   first_name=first_name)
        self.callback_query = None
        if callback_data is not None:
            self.callback_query = type("CallbackQuery", (), {
                "data": callback_data,
                "from_user": self.effective_user,
                "message": self.message,
                "answer": self._noop,
            })()

    @staticmethod
    async def _noop(*args, **kwargs):
        pass


class MockContext:
    """Minimal mock of telegram.ext.ContextTypes.DEFAULT_TYPE."""
    def __init__(self, bot=None):
        self.bot = bot or MockBot()
        self.user_data = {}
        self.args = []


@pytest.fixture
def mock_bot():
    return MockBot()


@pytest.fixture
def make_update():
    """Factory for MockUpdate objects."""
    def _make(user_id=0, text="", first_name="Test", username="testuser",
              callback_data=None):
        return MockUpdate(user_id, text, first_name, username, callback_data)
    return _make


@pytest.fixture
def make_context(mock_bot):
    """Factory for MockContext objects."""
    def _make(bot=None):
        return MockContext(bot=bot or mock_bot)
    return _make
