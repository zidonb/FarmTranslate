# BridgeOS Refactor — Complete Design Document

## What is BridgeOS

BridgeOS is a multi-bot Telegram translation system that connects managers with workers across language barriers. It runs 5 independent Telegram bot instances (one per connection slot), all sharing one PostgreSQL database. A manager can connect to up to 5 workers (one per bot). A worker connects to one manager only, via an invitation link that encodes which bot instance to use.

---

## Why Refactor

### Current Problems

**1. JSONB blob doing too much work**
Single `users` table with `data JSONB` column holds everything — role, language, gender, industry, invitation code, and a nested `workers` array. This makes queries complex and constraints impossible.

**2. Race conditions on the workers array**
Worker connection flow does read → modify → write on the manager's JSONB blob. Between read and write, another worker could connect. Defensive re-checks in Python narrow the window but can't close it. The `get-modify-save` pattern is not atomic.

**3. Orphaned references**
`worker['manager']` can point to a deleted manager. `manager['workers'][i]['worker_id']` can point to a deleted worker. No database-level referential integrity. Cleanup is reactive, not preventive.

**4. No database-level constraints**
Nothing prevents two workers claiming the same bot slot simultaneously. Nothing prevents corrupted role data. All validation in application code which can fail or be bypassed.

**5. 2500-line bot.py**
All handlers, registration flow, message handling, task management, subscription logic — everything in one file. Hard to navigate, hard to maintain.

**6. State detection is binary**
Can only detect "fully registered" or "not registered". Cannot detect intermediate registration states (user picked language but not gender). State lives in Telegram's in-memory `context.user_data` which evaporates on restart.

---

## Key Design Decisions

1. **Normalized relational schema** — separate tables for users, managers, workers, connections, messages, tasks, subscriptions, usage, feedback
2. **Database constraints prevent race conditions** — partial UNIQUE indexes on connections table make double-occupancy impossible at DB level
3. **No invitations table** — KISS. First worker to connect wins, second gets error from UNIQUE constraint. No pending state tracking needed.
4. **No registration_sessions table** — user can just re-register if interrupted. ConversationHandler with `allow_reentry=True` handles restarts.
5. **No services layer** — handlers call models directly. Not enough complexity to justify an extra abstraction layer yet.
6. **Soft deletes** on managers, workers. Connections use `status = 'disconnected'`. Preserves history.
7. **No migration needed** — only 3 test users (you, wife, friend). Drop and recreate.
8. **BIGINT user IDs** — Telegram IDs stored as native integers, no more string casting.
9. **`translation_msg_context.py` absorbed into `models/message.py`** — translation context is just "last N messages for a connection", no separate table needed.
10. **Split bot.py** into focused handler files grouped by functional area.
11. **Logging throughout** — `logging` module instead of print statements.
12. **TIMESTAMPTZ everywhere** — timezone-aware timestamps since users span multiple countries.

---

## Final Directory Structure

```
bridgeos/
├── bot.py                          # NEW — slim entry point, handler registration
├── schema.sql                      # NEW — database schema
├── dashboard.py                    # UPDATE LATER — not part of this refactor
├── config.py                       # KEEP — unchanged
├── config.json                     # KEEP — unchanged
├── requirements.txt                # KEEP — unchanged
├── runtime.txt                     # KEEP — unchanged
│
├── handlers/                       # NEW DIRECTORY
│   ├── __init__.py                 # Conversation states (LANGUAGE, GENDER, INDUSTRY)
│   ├── registration.py             # /start, language, gender, industry, cancel
│   ├── commands.py                 # /help, /menu, /reset, menu callback router
│   ├── connections.py              # /addworker, /workers
│   ├── tasks.py                    # /tasks, /daily, task creation (** prefix), task completion
│   ├── messages.py                 # handle_message, handle_media
│   └── subscriptions.py            # /subscription, /refer, /feedback
│
├── models/                         # NEW DIRECTORY
│   ├── __init__.py
│   ├── user.py                     # User CRUD (identity layer)
│   ├── manager.py                  # Manager CRUD + get_role() + get_by_code()
│   ├── worker.py                   # Worker CRUD
│   ├── connection.py               # Connection CRUD + SlotOccupiedError/WorkerAlreadyConnectedError
│   ├── message.py                  # Message CRUD + translation context (replaces message_history + translation_msg_context)
│   ├── task.py                     # Task CRUD (joins through connections)
│   ├── subscription.py             # Subscription CRUD + LemonSqueezy checkout URL
│   ├── usage.py                    # Usage tracking + atomic increment + limit enforcement
│   └── feedback.py                 # Feedback CRUD
│
├── utils/                          # MIXED (old + new)
│   ├── __init__.py                 # NEW
│   ├── db_connection.py            # KEEP — connection pool, unchanged
│   ├── translator.py               # KEEP — translation logic, unchanged
│   ├── i18n.py                     # KEEP — internationalization, unchanged
│   ├── logger.py                   # NEW — logging setup
│   └── helpers.py                  # NEW — bot slot detection, code generation, invite links
│
└── locales/                        # KEEP — unchanged
    ├── es.json
    └── (other locale files)
```

---

## Database Schema Summary

### Tables

1. **users** — identity layer (user_id PK, telegram_name, language, gender, timestamps)
2. **managers** — manager data (manager_id PK → users FK, code UNIQUE, industry, soft delete)
3. **workers** — worker data (worker_id PK → users FK, soft delete)
4. **connections** — the core relationship (manager_id, worker_id, bot_slot, status)
   - `UNIQUE(manager_id, bot_slot) WHERE status = 'active'` — prevents slot double-occupancy
   - `UNIQUE(worker_id) WHERE status = 'active'` — prevents worker having multiple managers
5. **messages** — communication history (connection_id FK, sender_id, original_text, translated_text)
6. **tasks** — task assignments (connection_id FK, description, description_translated, status)
7. **subscriptions** — LemonSqueezy billing (manager_id FK UNIQUE, external_id, status, portal URL)
8. **usage_tracking** — free tier limits (manager_id PK, messages_sent, is_blocked)
9. **feedback** — user feedback (user_id FK, message, status)

### Key Constraint: Race Condition Prevention
```sql
-- Only one active worker per manager per bot slot
CREATE UNIQUE INDEX idx_unique_manager_slot ON connections(manager_id, bot_slot) WHERE status = 'active';

-- Only one active connection per worker
CREATE UNIQUE INDEX idx_unique_active_worker ON connections(worker_id) WHERE status = 'active';
```

When two workers try to connect simultaneously, one INSERT succeeds, the other gets a `UniqueViolation` error. The database is the mutex.

---

## Files to Delete (replaced by new structure)

```
database.py                  → replaced by models/
message_history.py           → replaced by models/message.py
translation_msg_context.py   → replaced by models/message.py
subscription_manager.py      → replaced by models/subscription.py
usage_tracker.py             → replaced by models/usage.py
feedback.py                  → replaced by models/feedback.py
tasks.py                     → replaced by models/task.py
bot.py (old 2500-line)       → replaced by bot.py (new ~150 lines) + handlers/
```

---

## What Has Been Done

### ✅ Completed

1. **schema.sql** — full database schema with all tables, indexes, constraints, and triggers
2. **handlers/__init__.py** — conversation states
3. **handlers/registration.py** (~230 lines) — /start, language/gender/industry selection, worker registration with DB constraint-based race handling, cancel
4. **handlers/commands.py** (~175 lines) — /help, /menu, menu callback router, /reset with soft-delete + disconnect + notifications
5. **handlers/connections.py** (~145 lines) — /addworker (finds free slot, sends proactive message from next bot), /workers (shows all 5 slots)
6. **handlers/tasks.py** (~310 lines) — /tasks (manager/worker views grouped by worker), /daily (AI action items), task creation (** prefix), task completion callback, view tasks callback
7. **handlers/messages.py** (~260 lines) — handle_message (translate + forward for both roles, usage tracking), handle_media (forward as-is), usage limit helpers
8. **handlers/subscriptions.py** (~195 lines) — /subscription (free/active states), /refer, /feedback + feedback response handler
9. **models/__init__.py** — package marker
10. **models/user.py** (~85 lines) — identity CRUD with ON CONFLICT for safe re-registration
11. **models/manager.py** (~115 lines) — manager CRUD + get_role() + get_by_code() + code_exists()
12. **models/worker.py** (~45 lines) — worker CRUD with ON CONFLICT for re-activation after soft delete
13. **models/connection.py** (~175 lines) — connection CRUD with typed exceptions (SlotOccupiedError, WorkerAlreadyConnectedError), idempotent disconnect
14. **models/message.py** (~110 lines) — replaces message_history + translation_msg_context, probabilistic cleanup
15. **models/task.py** (~170 lines) — tasks join through connections, idempotent complete, worker tasks return translated description
16. **models/subscription.py** (~130 lines) — LemonSqueezy integration, is_active handles cancelled-but-not-expired
17. **models/usage.py** (~140 lines) — atomic increment, test user whitelist, limit enforcement
18. **models/feedback.py** (~55 lines) — save/get/mark_as_read

### ❌ Still To Do

1. **utils/__init__.py** — package marker
2. **utils/logger.py** — logging configuration setup
3. **utils/helpers.py** — get_bot_slot(), validate_invitation_code(), generate_invitation_code(), get_bot_username_for_slot(), get_invite_link()
4. **bot.py** (new version) — slim entry point with Application setup, handler registration, ConversationHandler wiring, main()
5. **dashboard.py** — update queries to use new schema (deferred, do after core works)

---

## Important Implementation Notes

### How handlers import models
```python
import models.user as user_model
import models.manager as manager_model
import models.connection as connection_model

user = user_model.get_by_id(user_id)
role = manager_model.get_role(user_id)
conn = connection_model.get_by_manager_and_slot(manager_id, bot_slot)
```

### How connection race conditions are handled
```python
try:
    connection_model.create(manager_id=manager_id, worker_id=user_id, bot_slot=bot_slot)
except connection_model.SlotOccupiedError:
    await update.message.reply_text("❌ This bot slot is already occupied.")
except connection_model.WorkerAlreadyConnectedError:
    await update.message.reply_text("❌ You're already connected to a manager.")
```

### How translation context works (replaces translation_msg_context.py)
```python
history = message_model.get_translation_context(conn['connection_id'], limit=context_size)
translated = translate(text=text, ..., conversation_history=history)
```

### Bot slot detection
Each bot instance knows its slot from the `BOT_ID` environment variable (`bot1` through `bot5`). The slot number is extracted by `utils/helpers.py:get_bot_slot()`.

### All models use the existing db_connection.py pool
```python
from utils.db_connection import get_db_cursor

with get_db_cursor() as cur:          # auto-commit
    cur.execute("INSERT INTO ...", (...))

with get_db_cursor(commit=False) as cur:  # read-only
    cur.execute("SELECT ...", (...))
```

---

## Existing Files That Are KEPT Unchanged

These files are independent of the database schema and work as-is:

- **config.py** — loads config.json
- **config.json** — industries, languages, limits, API keys
- **utils/db_connection.py** — PostgreSQL connection pool (ThreadedConnectionPool)
- **utils/translator.py** — translation via Claude/Gemini/OpenAI
- **utils/i18n.py** — loads locale JSON files, get_text() with fallback chain
- **locales/*.json** — translation strings per language
- **requirements.txt** — dependencies
- **runtime.txt** — Python version

---

## How to Continue

The remaining work is:
1. Create `utils/__init__.py`, `utils/logger.py`, `utils/helpers.py`
2. Create new `bot.py` (entry point with handler registration)
3. Run `schema.sql` against PostgreSQL to create tables
4. Test end-to-end with the 5 bot instances
5. Later: update `dashboard.py` to use new models
