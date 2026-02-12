# BridgeOS — Project Background

## What It Is

Telegram-based translation system connecting managers with foreign workers. Manager sends message in their language, worker receives it translated. And vice versa. Supports 12 languages (currently) with gender-aware grammar and industry-specific terminology.

5 independent bot instances (bot1–bot5) share one PostgreSQL database. Each manager can connect up to 5 workers, one per bot slot. Workers connect via deep-link invitation (e.g. `t.me/BridgeOS_2bot?start=invite_BRIDGE-12345`).

## Architecture

```
handlers/          → Telegram command/message handlers
models/            → Database access layer (one file per table)
utils/             → db_connection, translator, i18n, helpers, logger
bot.py             → Entry point (handler registration, ~90 lines)
dashboard.py       → Flask admin panel + LemonSqueezy webhooks
config.py          → Loads config.json + env vars / secrets.json
```

## Database (normalized relational, PostgreSQL)

- **users** — identity (user_id PK, telegram_name, language, gender)
- **managers** — manager data (code, industry, soft delete) FK → users
- **workers** — minimal (soft delete) FK → users
- **connections** — manager↔worker link (bot_slot 1-5, status active/disconnected)
  - UNIQUE(manager_id, bot_slot) WHERE active — prevents slot races at DB level
  - UNIQUE(worker_id) WHERE active — one manager per worker
- **messages** — chat history (connection_id, sender_id, original/translated text)
- **tasks** — task assignments (connection_id, description, status pending/completed)
- **subscriptions** — LemonSqueezy billing (manager_id, status, portal URL)
- **usage_tracking** — free tier limits (manager_id, messages_sent, is_blocked)
- **feedback** — user feedback

## Key Flows

**Registration**: /start → language → gender → industry (manager) or auto-connect (worker with invite code). Role determined by presence of invite code.

**Messaging**: User sends text → find connection for this bot slot → get translation context (last N messages) → translate with industry/gender context → forward to other party → save message.

**Tasks**: Manager sends `** task description` → translate → save to tasks table → send to worker with ✅ button → worker clicks done → notify manager.

**Subscriptions**: Free tier (configurable limit) → LemonSqueezy checkout → webhook updates DB → unlimited messages.

## Key Design Decisions

1. **Database constraints prevent race conditions** — no application-level locking needed
2. **Bot slot = which bot instance** (from BOT_ID env var), not encoded in invitation URL
3. **Soft deletes** on managers/workers, connections use status field
4. **i18n for UI** (get_text with locale JSON files), **LLM for conversations** (translator.py)
5. **Gender stored in English internally** ("Male"/"Female") — translator.py expects this
6. **Messages belong to connections**, not user pairs
7. **Translation context** = last N messages from same connection (replaces old separate table)

## Config

`config.json` holds: languages, industries, translation_provider, translation_context_size, free_message_limit, enforce_limits, testing_mode, test_user_ids, lemonsqueezy settings, claude/gemini/openai model configs.

Secrets come from env vars (Railway) or secrets.json (local).

## Deployment

Railway: worker service (bot.py) + web service (dashboard.py) + PostgreSQL. Each of the 5 bot instances is a separate Railway service with its own TELEGRAM_TOKEN and BOT_ID env var.

## Commands

**Manager**: /start, /help, /menu, /tasks, /daily, /addworker, /workers, /subscription, /refer, /feedback, /reset

**Worker**: /start, /help, /menu, /tasks, /refer, /feedback, /reset