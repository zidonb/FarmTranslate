-- =================================================================
-- BridgeOS Database Schema (Test Database)
-- Matches Railway production design with stricter FK constraints
-- + ON DELETE CASCADE on connections for clean user deletion
-- + 'paused' status for subscriptions (LemonSqueezy webhook support)
-- =================================================================

-- 1. Users: identity layer (role-agnostic)
-- Every person (manager or worker) has one row here.
CREATE TABLE IF NOT EXISTS users (
    user_id       BIGINT PRIMARY KEY,                -- Telegram user ID
    telegram_name VARCHAR(255),
    language      VARCHAR(50)  DEFAULT 'English',
    gender        VARCHAR(50),                       -- 'Male', 'Female', 'Prefer not to say'
    created_at    TIMESTAMPTZ  DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  DEFAULT NOW()
);

-- 2. Managers: manager-specific data (FK → users)
-- Uses soft delete (deleted_at) to preserve history.
CREATE TABLE IF NOT EXISTS managers (
    manager_id  BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    code        VARCHAR(20) NOT NULL,                -- e.g. 'BRIDGE-12345'
    industry    VARCHAR(50),                         -- key from config.json industries
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ                          -- NULL = active, non-NULL = soft-deleted
);

-- Code must be unique among active managers
CREATE UNIQUE INDEX IF NOT EXISTS idx_managers_active_code
    ON managers (code) WHERE deleted_at IS NULL;

-- 3. Workers: minimal worker record (FK → users)
-- Uses soft delete to preserve history.
CREATE TABLE IF NOT EXISTS workers (
    worker_id   BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ                          -- NULL = active, non-NULL = soft-deleted
);

-- 4. Connections: manager ↔ worker relationships
-- Each manager can have up to 5 workers (one per bot slot 1-5).
-- Each worker can be connected to exactly one manager at a time.
-- FKs reference managers/workers tables (not users) for role enforcement.
-- ON DELETE CASCADE ensures clean deletion when manager/worker is removed.
CREATE TABLE IF NOT EXISTS connections (
    connection_id   SERIAL PRIMARY KEY,
    manager_id      BIGINT NOT NULL REFERENCES managers(manager_id) ON DELETE CASCADE,
    worker_id       BIGINT NOT NULL REFERENCES workers(worker_id) ON DELETE CASCADE,
    bot_slot        INTEGER NOT NULL CHECK (bot_slot BETWEEN 1 AND 5),
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'disconnected')),
    connected_at    TIMESTAMPTZ DEFAULT NOW(),
    disconnected_at TIMESTAMPTZ
);

-- UNIQUE constraint: one worker per bot slot per manager (only active connections)
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_manager_slot
    ON connections (manager_id, bot_slot) WHERE status = 'active';

-- UNIQUE constraint: each worker can only have one active connection
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_worker
    ON connections (worker_id) WHERE status = 'active';

-- 5. Messages: chat history tied to connections
CREATE TABLE IF NOT EXISTS messages (
    message_id      SERIAL PRIMARY KEY,
    connection_id   INTEGER NOT NULL REFERENCES connections(connection_id) ON DELETE CASCADE,
    sender_id       BIGINT NOT NULL,
    original_text   TEXT NOT NULL,
    translated_text TEXT,
    sent_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_connection_sent
    ON messages (connection_id, sent_at);

-- 6. Tasks: task assignments tied to connections
CREATE TABLE IF NOT EXISTS tasks (
    task_id                SERIAL PRIMARY KEY,
    connection_id          INTEGER NOT NULL REFERENCES connections(connection_id) ON DELETE CASCADE,
    description            TEXT NOT NULL,
    description_translated TEXT,
    status                 VARCHAR(20) DEFAULT 'pending'
                               CHECK (status IN ('pending', 'completed')),
    created_at             TIMESTAMPTZ DEFAULT NOW(),
    completed_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tasks_connection
    ON tasks (connection_id);

-- 7. Subscriptions: LemonSqueezy billing per manager
-- Includes 'paused' status for LemonSqueezy subscription_paused webhook
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id     SERIAL PRIMARY KEY,
    manager_id          BIGINT UNIQUE NOT NULL REFERENCES users(user_id),
    external_id         VARCHAR(100),             -- LemonSqueezy subscription ID
    status              VARCHAR(30) DEFAULT 'active'
                            CHECK (status IN ('free', 'active', 'cancelled', 'expired', 'paused')),
    customer_portal_url TEXT,
    renews_at           TIMESTAMPTZ,
    ends_at             TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Usage tracking: free tier limits per manager
CREATE TABLE IF NOT EXISTS usage_tracking (
    manager_id       BIGINT PRIMARY KEY REFERENCES users(user_id),
    messages_sent    INTEGER DEFAULT 0,
    is_blocked       BOOLEAN DEFAULT FALSE,
    first_message_at TIMESTAMPTZ,
    last_message_at  TIMESTAMPTZ
);

-- 9. Feedback: user feedback
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id    SERIAL PRIMARY KEY,
    user_id        BIGINT,
    telegram_name  VARCHAR(255),
    username       VARCHAR(255),
    message        TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    status         VARCHAR(20) DEFAULT 'unread'
);
