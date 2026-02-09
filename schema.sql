-- ============================================
-- BridgeOS Database Schema
-- PostgreSQL normalized relational design
-- ============================================

-- Drop existing tables (clean slate - no migration needed)
DROP TABLE IF EXISTS feedback CASCADE;
DROP TABLE IF EXISTS usage_tracking CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS connections CASCADE;
DROP TABLE IF EXISTS workers CASCADE;
DROP TABLE IF EXISTS managers CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- ============================================
-- CORE TABLES
-- ============================================

-- Identity layer - every person in the system
CREATE TABLE users (
    user_id         BIGINT PRIMARY KEY,             -- Telegram user ID
    telegram_name   TEXT,                            -- First name from Telegram
    language        TEXT NOT NULL,                   -- Display language name (e.g. 'English', 'עברית')
    gender          TEXT,                            -- 'Male', 'Female', 'Prefer not to say'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Manager-specific data
CREATE TABLE managers (
    manager_id      BIGINT PRIMARY KEY,
    code            TEXT UNIQUE NOT NULL,            -- Invitation code: 'BRIDGE-12345'
    industry        TEXT NOT NULL,                   -- Industry key from config.json
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,                     -- NULL = active (soft delete)

    FOREIGN KEY (manager_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_managers_active ON managers(manager_id) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX idx_managers_code_active ON managers(code) WHERE deleted_at IS NULL;

-- Worker-specific data
CREATE TABLE workers (
    worker_id       BIGINT PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,                     -- NULL = active (soft delete)

    FOREIGN KEY (worker_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_workers_active ON workers(worker_id) WHERE deleted_at IS NULL;

-- Manager-worker relationships
CREATE TABLE connections (
    connection_id   SERIAL PRIMARY KEY,
    manager_id      BIGINT NOT NULL,
    worker_id       BIGINT NOT NULL,
    bot_slot        INTEGER NOT NULL CHECK (bot_slot BETWEEN 1 AND 5),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'disconnected')),
    connected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    disconnected_at TIMESTAMPTZ,

    FOREIGN KEY (manager_id) REFERENCES managers(manager_id),
    FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
);

-- One active worker per manager per bot slot (race condition prevention)
CREATE UNIQUE INDEX idx_unique_manager_slot
    ON connections(manager_id, bot_slot)
    WHERE status = 'active';

-- One active connection per worker (worker can only have one manager)
CREATE UNIQUE INDEX idx_unique_active_worker
    ON connections(worker_id)
    WHERE status = 'active';

-- Fast lookup: active connections for a manager
CREATE INDEX idx_connections_manager_active
    ON connections(manager_id)
    WHERE status = 'active';

-- ============================================
-- COMMUNICATION
-- ============================================

CREATE TABLE messages (
    message_id      BIGSERIAL PRIMARY KEY,
    connection_id   INTEGER NOT NULL,
    sender_id       BIGINT NOT NULL,
    original_text   TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (connection_id) REFERENCES connections(connection_id),
    FOREIGN KEY (sender_id) REFERENCES users(user_id)
);

-- Fast lookup: recent messages for translation context
CREATE INDEX idx_messages_connection_recent
    ON messages(connection_id, sent_at DESC);

-- ============================================
-- TASKS
-- ============================================

CREATE TABLE tasks (
    task_id             SERIAL PRIMARY KEY,
    connection_id       INTEGER NOT NULL,
    description         TEXT NOT NULL,                -- Manager's language
    description_translated TEXT,                      -- Worker's language
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'completed', 'cancelled')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,

    FOREIGN KEY (connection_id) REFERENCES connections(connection_id)
);

CREATE INDEX idx_tasks_connection_pending
    ON tasks(connection_id)
    WHERE status = 'pending';

-- ============================================
-- BILLING & USAGE
-- ============================================

CREATE TABLE subscriptions (
    subscription_id SERIAL PRIMARY KEY,
    manager_id      BIGINT NOT NULL UNIQUE,
    external_id     TEXT,                            -- LemonSqueezy subscription ID
    status          TEXT NOT NULL DEFAULT 'free'
                    CHECK (status IN ('free', 'active', 'cancelled', 'expired')),
    customer_portal_url TEXT,
    renews_at       TIMESTAMPTZ,
    ends_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (manager_id) REFERENCES managers(manager_id)
);

CREATE TABLE usage_tracking (
    manager_id      BIGINT PRIMARY KEY,
    messages_sent   INTEGER NOT NULL DEFAULT 0,
    is_blocked      BOOLEAN NOT NULL DEFAULT FALSE,
    first_message_at TIMESTAMPTZ,
    last_message_at TIMESTAMPTZ,

    FOREIGN KEY (manager_id) REFERENCES managers(manager_id)
);

-- ============================================
-- FEEDBACK
-- ============================================

CREATE TABLE feedback (
    feedback_id     SERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    telegram_name   TEXT,
    username        TEXT,                            -- @username
    message         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          TEXT NOT NULL DEFAULT 'unread'
                    CHECK (status IN ('unread', 'read')),

    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- ============================================
-- HELPER FUNCTION: auto-update updated_at
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_subscriptions_updated_at
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
